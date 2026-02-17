#!/usr/bin/env python3
"""Fetch S&P 500 constituent tickers from public sources and write ml/sp500.txt.
Tries datahub and Wikipedia raw CSVs; falls back to a small built-in list.
"""
import requests
import os

OUT = "ml/sp500.txt"

SOURCES = [
    "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv",
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv",
]

FALLBACK = [
    "AAPL","MSFT","AMZN","GOOGL","GOOG","FB","TSLA","BRK.B","JPM","JNJ",
]

def try_fetch():
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            lines = r.text.splitlines()
            tickers = []
            for i, line in enumerate(lines):
                if i == 0:
                    # header
                    continue
                parts = line.split(',')
                if parts:
                    sym = parts[0].strip().strip('"')
                    if sym:
                        tickers.append(sym)
            if tickers:
                return tickers
        except Exception:
            continue
    return None

def main():
    tickers = try_fetch()
    if not tickers:
        tickers = FALLBACK
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        for t in tickers:
            f.write(t + '\n')
    print('Wrote', len(tickers), 'tickers to', OUT)

if __name__ == '__main__':
    main()
