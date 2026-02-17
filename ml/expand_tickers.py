#!/usr/bin/env python3
"""Expand tickers list by downloading NASDAQ/NASDAQ other-listed files,
filter by MarketCapitalization > $1B and monthly history length >= 60 months.

Writes `ml/expanded_tickers_1000.txt` containing up to target tickers.
"""
import os
import time
import requests
import math
import argparse
from datetime import datetime

API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")


class RateLimiter:
    def __init__(self, calls_per_minute: int):
        self.min_interval = 60.0 / max(1, calls_per_minute)
        self._last = 0.0

    def wait(self):
        now = time.time()
        elapsed = now - self._last
        to_wait = self.min_interval - elapsed
        if to_wait > 0:
            time.sleep(to_wait)
        self._last = time.time()


def fetch_symbol_lists():
    urls = [
        "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]
    symbols = set()
    for url in urls:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        for line in r.text.splitlines():
            if not line or line.startswith("Symbol") or line.startswith("File Creation"):
                continue
            parts = line.split('|')
            if len(parts) >= 1:
                sym = parts[0].strip()
                # skip test/placeholder
                if sym and sym.upper() not in ("FILE",):
                    symbols.add(sym)
    return sorted(symbols)


def safe_get(session, url, params, rl, max_retries=3):
    for attempt in range(max_retries):
        try:
            rl.wait()
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
        except Exception:
            time.sleep(2 ** attempt)
    return None


def monthly_length(monthly_json):
    if not monthly_json:
        return 0
    for k in ("Monthly Adjusted Time Series", "Monthly Adjusted", "Time Series (Monthly)"):
        if k in monthly_json:
            return len(monthly_json[k])
    keys = [k for k in monthly_json.keys() if k.lower().startswith("time series")]
    if keys:
        return len(monthly_json[keys[0]])
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=1000)
    parser.add_argument("--min_mcap", type=float, default=1e9)
    parser.add_argument("--min_months", type=int, default=60)
    parser.add_argument("--out", default="ml/expanded_tickers_1000.txt")
    args = parser.parse_args()

    if not API_KEY:
        print("Missing ALPHAVANTAGE_API_KEY in environment")
        return

    symbols = fetch_symbol_lists()
    print(f"Fetched {len(symbols)} candidate symbols")

    session = requests.Session()
    rl = RateLimiter(calls_per_minute=300)
    base = "https://www.alphavantage.co/query"

    winners = []
    for i, s in enumerate(symbols, 1):
        if len(winners) >= args.target:
            break
        print(f"[{i}/{len(symbols)}] checking {s} (found {len(winners)})")
        # overview for market cap
        ov = safe_get(session, base, {"function": "OVERVIEW", "symbol": s, "apikey": API_KEY}, rl)
        try:
            mcap = ov and float(ov.get("MarketCapitalization") or ov.get("MarketCapitalization", 0))
        except Exception:
            mcap = 0
        if not mcap or mcap < args.min_mcap:
            continue
        # check monthly
        monthly = safe_get(session, base, {"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": s, "apikey": API_KEY}, rl)
        mlen = monthly_length(monthly)
        if mlen >= args.min_months:
            winners.append(s)
        # small sleep to be gentle
    print(f"Selected {len(winners)} symbols; writing to {args.out}")
    with open(args.out, 'w') as f:
        for w in winners:
            f.write(w + '\n')


if __name__ == '__main__':
    main()
