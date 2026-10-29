import time
from datetime import date, timedelta

import pandas as pd
import requests

BASE_URL = "https://data.alpaca.markets/v2"
RETRY_STATUS = {429, 500, 502, 503, 504}


def _headers():
    import os

    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError(
            "ALPACA_API_KEY and ALPACA_API_SECRET GitHub secrets are required."
        )

    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }


def _get(url, params, retries=3):
    last_error = None

    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                headers=_headers(),
                params=params,
                timeout=30,
            )

            if response.status_code in RETRY_STATUS:
                last_error = RuntimeError(f"HTTP {response.status_code}")
                time.sleep(1.5 * (attempt + 1))
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))

    raise last_error or RuntimeError("Alpaca request failed")


def _as_frame(symbol, bars):
    if not bars:
        return pd.DataFrame()

    rows = []
    for bar in bars:
        rows.append(
            {
                "symbol": symbol,
                "timestamp": bar["t"],
                "open": float(bar["o"]),
                "high": float(bar["h"]),
                "low": float(bar["l"]),
                "close": float(bar["c"]),
                "volume": float(bar["v"]),
            }
        )

    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values("timestamp").reset_index(drop=True)


def historical_daily(symbols, calendar_days=400, batch_size=100):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=calendar_days)
    frames = []

    symbols = list(dict.fromkeys(symbols))

    for offset in range(0, len(symbols), batch_size):
        batch = symbols[offset : offset + batch_size]
        params = {
            "symbols": ",".join(batch),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "split",
            "feed": "iex",
            "limit": 10000,
        }

        page_token = None

        while True:
            if page_token:
                params["page_token"] = page_token
            else:
                params.pop("page_token", None)

            payload = _get(f"{BASE_URL}/stocks/bars", params)
            bars_by_symbol = payload.get("bars", {})

            for symbol, bars in bars_by_symbol.items():
                frame = _as_frame(symbol, bars)
                if not frame.empty:
                    frames.append(frame)

            page_token = payload.get("next_page_token")
            if not page_token:
                break

            time.sleep(0.4)

        print(
            f"Historical batch {min(offset + batch_size, len(symbols))}/"
            f"{len(symbols)}"
        )
        time.sleep(0.4)

    if not frames:
        return pd.DataFrame(
            columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        )

    return pd.concat(frames, ignore_index=True)


def split_by_symbol(frame):
    if frame.empty:
        return {}

    return {
        symbol: group.sort_values("timestamp").reset_index(drop=True)
        for symbol, group in frame.groupby("symbol")
    }
