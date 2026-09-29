import math
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from scanner.indicators import ema, atr
from scanner.vcp import detect_vcp
from config import settings

IST = ZoneInfo("Asia/Kolkata")

def _completed(df):
    if df.empty:
        return df
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"])
    today = datetime.now(IST).date()
    return x[x["timestamp"].dt.date < today].sort_values("timestamp").reset_index(drop=True)

def build_state(symbol, df, nifty_df):
    x = _completed(df)
    n = _completed(nifty_df) if nifty_df is not None else nifty_df
    if len(x) < 260:
        return None

    x["ema21"] = ema(x["close"], 21)
    x["atr14"] = atr(x, 14)
    last = x.iloc[-1]
    price = float(last.close)
    atr_pct = float(last.atr14 / price * 100)
    h52 = float(x.high.iloc[-252:].max())
    l52 = float(x.low.iloc[-252:].min())
    from_high = (h52 - price) / h52 * 100
    swing = (price / l52 - 1) * 100
    avg_volume = float(x.volume.iloc[-21:].mean())

    red = x.iloc[-11:]
    red_vol = red.loc[red.close < red.open, "volume"].max()

    vcp = detect_vcp(x)
    rs20 = np.nan
    if n is not None and len(n) >= 25:
        rs20 = ((price / x.close.iloc[-21] - 1) -
                (n.close.iloc[-1] / n.close.iloc[-21] - 1)) * 100

    pivot = max(float(x.high.iloc[-1]), float(x.close.iloc[-1])) * (
        1 + settings.BREAKOUT_BUFFER_PCT / 100
    )

    return {
        "symbol": symbol,
        "ema21": float(last.ema21),
        "atr_pct": atr_pct,
        "year_high": h52,
        "year_low": l52,
        "from_high": from_high,
        "swing": swing,
        "avg_volume": avg_volume,
        "red_max_volume": float(red_vol) if np.isfinite(red_vol) else 0.0,
        "prev_close": float(last.close),
        "prev_high": float(last.high),
        "pivot": pivot,
        "rs20": float(rs20) if np.isfinite(rs20) else np.nan,
        "vcp": vcp["true_vcp"],
        "vcp_breakout": False,
        "vcp_quality": vcp["quality_score"],
        "vcp_failed": ";".join(vcp["reasons"]),
    }

def _market_minutes():
    now = datetime.now(IST)
    start = datetime.combine(now.date(), dtime(9, 15), tzinfo=IST)
    end = datetime.combine(now.date(), dtime(15, 30), tzinfo=IST)
    return (now - start).total_seconds() / 60, start, end

def evaluate(state, quote):
    minutes, _, _ = _market_minutes()
    if minutes < 15:
        return None

    price = float(quote.get("last_price") or 0)
    volume = float(quote.get("volume") or quote.get("ohlc", {}).get("volume") or 0)
    day_open = float(quote.get("ohlc", {}).get("open") or 0)
    if price <= 0 or volume <= 0:
        return None

    # Project today's volume to a full trading day so RVOL is not inflated at the open.
    elapsed_fraction = min(max(minutes / 375.0, 0.05), 1.0)
    projected_rvol = (
        volume / (state["avg_volume"] * elapsed_fraction)
        if state["avg_volume"] > 0 else 0
    )

    pocket = (
        price > day_open and volume > state["red_max_volume"]
        if state["red_max_volume"] > 0 else False
    )
    normal_breakout = price >= state["pivot"]
    momentum = price > state["prev_close"]
    above_ema = price > state["ema21"]
    liquidity = price * volume >= settings.MIN_TURNOVER_CR * 1e7

    parts = {
        "trend": above_ema,
        "near_high": state["from_high"] <= settings.CANDIDATE_NEAR_HIGH_PCT,
        "vcp": state["vcp"],
        "swing": state["swing"] >= settings.CANDIDATE_MIN_SWING,
        "liquidity": liquidity,
        "momentum": momentum,
    }
    score = sum(bool(v) for v in parts.values())

    entry = all([
        price >= settings.MIN_PRICE,
        above_ema,
        momentum,
        projected_rvol >= settings.MIN_RVOL or pocket,
        normal_breakout or state["vcp_breakout"],
        state["atr_pct"] >= settings.MIN_ATR_PCT,
        state["swing"] >= settings.MIN_SWING_RETURN,
        state["from_high"] <= settings.MAX_FROM_52W_HIGH,
        liquidity,
    ])

    return {
        **state,
        "price": price,
        "volume": volume,
        "rvol": projected_rvol,
        "pocket_pivot": pocket,
        "breakout": normal_breakout,
        "score": score,
        "candidate": score >= settings.CANDIDATE_SCORE_REQUIRED,
        "buy": bool(entry),
        "timestamp": quote.get("timestamp", ""),
    }
