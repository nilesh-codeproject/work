import csv
from io import StringIO

import requests

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

EXCHANGES = {"A", "N", "P", "Z", "V"}
EXCLUDED_NAME_PATTERNS = (
    "WARRANT",
    "RIGHT",
    "UNIT",
    "PREFERRED",
    "DEPOSITARY",
    "NOTE",
    "BOND",
)


def _download(url):
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 us-free-scanner/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def _is_common_stock_name(name):
    upper = str(name).upper()
    return not any(pattern in upper for pattern in EXCLUDED_NAME_PATTERNS)


def _parse_nasdaq_listed(text):
    reader = csv.DictReader(StringIO(text), delimiter="|")
    symbols = set()

    for row in reader:
        symbol = str(row.get("Symbol", "")).strip().upper()
        if not symbol or symbol == "FILE CREATION TIME":
            continue
        if str(row.get("Test Issue", "")).upper() == "Y":
            continue
        financial_status = str(row.get("Financial Status", "")).upper()
        if financial_status and financial_status != "N":
            continue
        if str(row.get("ETF", "")).upper() == "Y":
            continue

        name = str(row.get("Security Name", "")).strip()
        if not _is_common_stock_name(name):
            continue

        symbols.add(symbol)

    return symbols


def _parse_other_listed(text):
    reader = csv.DictReader(StringIO(text), delimiter="|")
    symbols = set()

    for row in reader:
        symbol = str(
            row.get("NASDAQ Symbol")
            or row.get("CQS Symbol")
            or row.get("ACT Symbol")
            or ""
        ).strip().upper()

        if not symbol or symbol == "FILE CREATION TIME":
            continue
        if str(row.get("Test Issue", "")).upper() == "Y":
            continue
        if str(row.get("ETF", "")).upper() == "Y":
            continue

        exchange = str(row.get("Exchange", "")).upper()
        if exchange not in EXCHANGES:
            continue

        name = str(row.get("Security Name", "")).strip()
        if not _is_common_stock_name(name):
            continue

        symbols.add(symbol)

    return symbols


def load_us_equity_universe():
    nasdaq = _parse_nasdaq_listed(_download(NASDAQ_LISTED_URL))
    other = _parse_other_listed(_download(OTHER_LISTED_URL))
    symbols = sorted(nasdaq | other)

    if not symbols:
        raise RuntimeError("US equity universe could not be loaded from Nasdaq Trader.")

    print(f"NASDAQ-listed common-stock symbols: {len(nasdaq)}")
    print(f"Other US exchange-listed symbols: {len(other)}")
    print(f"US equity universe after de-duplication: {len(symbols)}")
    return symbols
