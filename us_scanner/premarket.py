from datetime import date

import pandas as pd


PRICE_FLOOR = 5.0
MIN_AVG_DOLLAR_VOLUME = 5_000_000.0
MIN_CANDIDATE_SCORE = 4
MAX_CANDIDATES = 30


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _atr_pct(frame, length=14):
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = true_range.rolling(length).mean().iloc[-1]
    close = frame["close"].iloc[-1]

    if pd.isna(atr) or close <= 0:
        return 0.0

    return float(atr / close * 100.0)


def score_symbol(frame):
    if len(frame) < 60:
        return None

    frame = frame.sort_values("timestamp").reset_index(drop=True)
    close = float(frame["close"].iloc[-1])
    previous_close = float(frame["close"].iloc[-2])
    avg_volume20 = float(frame["volume"].iloc[-21:-1].mean())
    avg_dollar_volume20 = float(
        (frame["close"].iloc[-21:-1] * frame["volume"].iloc[-21:-1]).mean()
    )

    ema21 = float(_ema(frame["close"], 21).iloc[-1])
    year_high = float(frame["high"].iloc[-252:].max())
    year_low = float(frame["low"].iloc[-252:].min())
    swing60 = float((close / frame["close"].iloc[-61] - 1.0) * 100.0)
    distance_high = float((year_high - close) / year_high * 100.0)
    rvol_daily = (
        float(frame["volume"].iloc[-1] / avg_volume20)
        if avg_volume20 > 0
        else 0.0
    )
    atr_pct = _atr_pct(frame)

    checks = {
        "trend": close > ema21,
        "near_high": distance_high <= 20.0,
        "swing60": swing60 >= 15.0,
        "daily_rvol": rvol_daily >= 1.20,
        "momentum": close > previous_close,
        "volatility": atr_pct >= 2.5,
        "liquidity": avg_dollar_volume20 >= MIN_AVG_DOLLAR_VOLUME,
    }

    score = sum(checks.values())

    if close < PRICE_FLOOR or not checks["liquidity"] or score < MIN_CANDIDATE_SCORE:
        return None

    return {
        "symbol": str(frame["symbol"].iloc[-1]),
        "last_close": close,
        "previous_close": previous_close,
        "ema21": ema21,
        "year_high": year_high,
        "year_low": year_low,
        "from_52w_high_pct": distance_high,
        "swing60_pct": swing60,
        "rvol_daily": rvol_daily,
        "atr_pct": atr_pct,
        "avg_dollar_volume20": avg_dollar_volume20,
        "checks_passed": score,
    }


def build_candidates(frame):
    candidates = []

    for symbol, group in frame.groupby("symbol"):
        result = score_symbol(group)
        if result:
            candidates.append(result)

    candidates = sorted(
        candidates,
        key=lambda row: (
            row["checks_passed"],
            row["avg_dollar_volume20"],
            row["swing60_pct"],
        ),
        reverse=True,
    )

    return candidates[:MAX_CANDIDATES]


def run_premarket():
    from us_scanner.universe import load_us_equity_universe
    from us_scanner.alpaca_data import historical_daily

    symbols = load_us_equity_universe()

    # First pass: 60+ calendar days across the complete US common-stock universe.
    # This keeps the scan broad while avoiding a 252-day download for every symbol.
    first_pass = historical_daily(symbols, calendar_days=110)
    first_candidates = build_candidates(first_pass)

    print(
        f"First-pass candidates: {len(first_candidates)} "
        f"from {len(symbols)} universe symbols"
    )

    first_symbols = [row["symbol"] for row in first_candidates]

    # Deep pass: 252-trading-day context for the strongest first-pass names.
    deep_symbols = first_symbols
    deep = historical_daily(deep_symbols, calendar_days=400)
    candidates = build_candidates(deep)

    # Keep a hard maximum of 30 candidates for the free Alpaca WebSocket.
    candidates = candidates[:MAX_CANDIDATES]

    today = date.today().isoformat()
    output = pd.DataFrame(candidates)
    if output.empty:
        output = pd.DataFrame(
            columns=[
                "scan_date",
                "symbol",
                "last_close",
                "previous_close",
                "ema21",
                "year_high",
                "year_low",
                "from_52w_high_pct",
                "swing60_pct",
                "rvol_daily",
                "atr_pct",
                "avg_dollar_volume20",
                "checks_passed",
            ]
        )
    else:
        output.insert(0, "scan_date", today)

    output.to_csv("us_candidates.csv", index=False)

    print(f"Final real-time candidate count: {len(output)}")
    print(output.to_string(index=False))
    return output


if __name__ == "__main__":
    run_premarket()
