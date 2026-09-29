import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd
import upstox_client
from google.protobuf.json_format import MessageToDict

from config import settings
from scanner.alerts import send
from scanner.live_engine import build_state, evaluate
from scanner.upstox import load_nse_equities, find_nifty500_key, historical_daily, historical_many

IST = ZoneInfo("Asia/Kolkata")

def as_dict(message):
    if isinstance(message, dict):
        return message
    try:
        return MessageToDict(message, preserving_proto_field_name=False)
    except Exception:
        return {}

def extract_quote(feed):
    full = feed.get("ff") or feed.get("fullFeed") or feed.get("full_feed") or {}
    market = full.get("marketFF") or full.get("market_ff") or {}
    ltpc = market.get("ltpc") or {}
    details = market.get("eFeedDetails") or market.get("e_feed_details") or {}
    ohlc_block = market.get("marketOHLC") or market.get("market_ohlc") or {}
    candles = ohlc_block.get("ohlc") or []
    daily = next((c for c in candles if c.get("interval") == "1d"), candles[0] if candles else {})
    ltp = ltpc.get("ltp")
    volume = details.get("vtt")
    if volume is None:
        volume = daily.get("vol") or daily.get("volume")
    return {
        "last_price": float(ltp) if ltp is not None else 0.0,
        "volume": float(volume) if volume is not None else 0.0,
        "ohlc": {"open": float(daily.get("open")) if daily.get("open") is not None else 0.0},
        "timestamp": str(feed.get("currentTs", "")),
    }

def fmt_alert(kind, r):
    emoji = "🚨" if kind == "BUY" else "📈"
    return (
        f"{emoji} {kind} SIGNAL — {r['symbol']}\n"
        f"Price ₹{r['price']:.2f} | Pivot ₹{r['pivot']:.2f}\n"
        f"Score {r['score']}/7 | RVOL {r['rvol']:.2f}x | ATR {r['atr_pct']:.2f}%\n"
        f"RS20 {r['rs20']:.2f}% | 52W from high {r['from_high']:.2f}%\n"
        f"Swing {r['swing']:.1f}% | VCP quality {r['vcp_quality']} | Pocket Pivot {r['pocket_pivot']}\n"
        f"Live scanner only — no order placed."
    )

def market_open_close():
    now = datetime.now(IST)
    start = datetime.combine(now.date(), dtime(9, 15), tzinfo=IST)
    end = datetime.combine(now.date(), dtime(15, 20), tzinfo=IST)
    return start, end

def run():
    universe = load_nse_equities()
    nifty_key = find_nifty500_key()
    nifty_df = historical_daily(nifty_key, years=2)
    print(f"Preparing live states for {len(universe)} NSE equities...")
    data = historical_many(universe, years=2, max_workers=settings.UPSTOX_MAX_WORKERS)

    states = {}
    for _, row in universe.iterrows():
        symbol = row.trading_symbol
        _, df, error = data.get(row.instrument_key, (symbol, pd.DataFrame(), "missing"))
        if error or df.empty or len(df) < 260:
            continue
        try:
            state = build_state(symbol, df, nifty_df)
            if state:
                states[row.instrument_key] = state
        except Exception as exc:
            print(f"[{symbol}] state build failed: {exc}")

    print(f"Live-ready symbols: {len(states)}")
    if not states:
        raise RuntimeError("No symbols have enough historical data for live monitoring.")

    send(
        f"🟢 NSE LIVE SCANNER STARTED\n"
        f"Monitoring {len(states)} symbols via Upstox WebSocket.\n"
        f"No orders will be placed."
    )

    configuration = upstox_client.Configuration()
    configuration.access_token = settings.UPSTOX_ACCESS_TOKEN
    client = upstox_client.ApiClient(configuration)
    keys = list(states.keys())
    streamer = upstox_client.MarketDataStreamerV3(client, keys, "full")
    streamer.auto_reconnect(True, 10, 20)

    sent_breakout = set()
    sent_buy = set()
    last_log = 0.0

    def on_open():
        print(f"WebSocket connected; subscribed to {len(keys)} instruments.")
        send("🟢 Upstox WebSocket connected. Live signal monitoring is active.")

    def on_error(message):
        print(f"WebSocket error: {message}")

    def on_close(message):
        print(f"WebSocket closed: {message}")

    def on_message(message):
        nonlocal last_log
        raw = as_dict(message)
        for instrument_key, feed in (raw.get("feeds") or {}).items():
            state = states.get(instrument_key)
            if not state:
                continue
            try:
                quote = extract_quote(feed)
                result = evaluate(state, quote)
                if not result:
                    continue
                symbol = state["symbol"]
                # Telegram alerts are restricted to final BUY signals only.
                if result["buy"] and symbol not in sent_buy:
                    sent_buy.add(symbol)
                    send(fmt_alert("BUY", result))
            except Exception as exc:
                print(f"[{instrument_key}] tick processing failed: {exc}")

        now = time.time()
        if now - last_log >= 60:
            last_log = now
            print(
                f"Heartbeat {datetime.now(IST).strftime('%H:%M:%S')} | "
                f"breakout alerts={len(sent_breakout)} | buy alerts={len(sent_buy)}"
            )

    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)

    start, end = market_open_close()
    while datetime.now(IST) < start:
        time.sleep(5)

    streamer.connect()
    try:
        while datetime.now(IST) < end:
            time.sleep(10)
    finally:
        try:
            streamer.disconnect()
        except Exception:
            pass
        send("🔴 NSE LIVE SCANNER STOPPED for the session.")

if __name__ == "__main__":
    run()
