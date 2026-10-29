import json
import os
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import pandas as pd
import websocket

from us_scanner.alerts import send

ET = ZoneInfo("America/New_York")
STREAM_URL = "wss://stream.data.alpaca.markets/v2/iex"
ORB_WINDOWS = (3, 5, 15, 30, 60)
BREAKOUT_BUFFER_PCT = 0.50
MIN_RVOL = 1.30
PRICE_FLOOR = 5.0

def _credentials():
    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY and ALPACA_API_SECRET are required.")
    return key, secret

def _load_candidates(path="us_candidates.csv"):
    frame = pd.read_csv(path)
    if frame.empty:
        raise RuntimeError("us_candidates.csv is empty.")
    frame = frame.head(30).copy()
    return frame

def _opening_range_high(bars, minutes):
    start_minute = 9 * 60 + 30
    end_minute = start_minute + minutes
    highs = []
    for bar in bars:
        minute = bar["timestamp"].hour * 60 + bar["timestamp"].minute
        if start_minute <= minute < end_minute:
            highs.append(bar["high"])
    return max(highs) if highs else None

def _evaluate(state, bar):
    session_minutes = (bar["timestamp"].hour * 60 + bar["timestamp"].minute) - (9 * 60 + 30)
    if session_minutes < 3:
        state["bars"].append(bar)
        state["cumulative_volume"] += bar["volume"]
        return None

    state["bars"].append(bar)
    state["cumulative_volume"] += bar["volume"]
    price = bar["close"]
    if price <= PRICE_FLOOR:
        return None

    orb_windows = []
    for window in ORB_WINDOWS:
        high = _opening_range_high(state["bars"], window)
        if high is not None and session_minutes >= window and price > high:
            orb_windows.append(window)

    elapsed_fraction = max(session_minutes, 1) / 390.0
    avg_volume = state["avg_volume20"]
    projected_rvol = (
        state["cumulative_volume"] / avg_volume / elapsed_fraction
        if avg_volume > 0 else 0.0
    )

    previous_close = state["previous_close"]
    breakout_level = previous_close * (1 + BREAKOUT_BUFFER_PCT / 100.0)
    breakout = price > breakout_level
    momentum = price > previous_close

    if not (orb_windows and projected_rvol >= MIN_RVOL and breakout and momentum):
        return None

    return {
        "price": price,
        "rvol": projected_rvol,
        "orb_windows": orb_windows,
        "breakout_level": breakout_level,
        "timestamp": bar["timestamp"],
    }

def run():
    candidates = _load_candidates()
    symbols = [str(x).upper() for x in candidates["symbol"].tolist()]
    state = {
        row.symbol: {
            "previous_close": float(row.previous_close),
            "avg_volume20": float(row.avg_volume20),
            "bars": [],
            "cumulative_volume": 0.0,
            "alerted": False,
        }
        for row in candidates.itertuples(index=False)
    }
    key, secret = _credentials()

    send(
        "🇺🇸 US LIVE SCANNER STARTED\n"
        f"Monitoring {len(symbols)} shortlisted stocks via Alpaca IEX.\n"
        "Alert-only mode — no orders will be placed."
    )

    def on_open(ws):
        ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
        time.sleep(1)
        ws.send(json.dumps({"action": "subscribe", "bars": symbols}))
        print(f"Subscribed to {len(symbols)} candidates.")

    def on_message(ws, raw_message):
        for message in json.loads(raw_message):
            if message.get("T") != "b":
                continue
            symbol = message["S"]
            if symbol not in state:
                continue
            ts = pd.to_datetime(message["t"], utc=True).tz_convert(ET)
            bar = {
                "timestamp": ts,
                "high": float(message["h"]),
                "close": float(message["c"]),
                "volume": float(message["v"]),
            }
            result = _evaluate(state[symbol], bar)
            if result and not state[symbol]["alerted"]:
                state[symbol]["alerted"] = True
                ranges = ", ".join(f"{x}m" for x in result["orb_windows"])
                send(
                    f"🚨 US MOMENTUM BUY - {symbol}\n"
                    f"Price ${result['price']:.2f}\n"
                    f"Projected RVOL {result['rvol']:.2f}x\n"
                    f"ORB break: {ranges}\n"
                    f"Breakout level ${result['breakout_level']:.2f}\n"
                    f"Time {result['timestamp'].strftime('%H:%M:%S ET')}\n"
                    "Free US scanner — alert only.",
                    chart_symbol=symbol,
                )

    def on_error(ws, error):
        print(f"Alpaca WebSocket error: {error}")

    def on_close(ws, code, message):
        print(f"Alpaca WebSocket closed: {code} | {message}")

    now = datetime.now(ET)
    market_open = datetime.combine(now.date(), dt_time(9, 30), tzinfo=ET)
    market_close = datetime.combine(now.date(), dt_time(16, 0), tzinfo=ET)
    startup_window_start = market_open - pd.Timedelta(minutes=15)
    startup_window_end = market_open + pd.Timedelta(minutes=15)
    if now < startup_window_start or now > startup_window_end:
        print(
            f"US live workflow started outside the market-open window: {now.isoformat()}"
        )
        return

    ws = websocket.WebSocketApp(
        STREAM_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(ping_interval=20, ping_timeout=10)


if __name__ == "__main__":
    run()