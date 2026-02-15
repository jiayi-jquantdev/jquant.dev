#!/usr/bin/env python3
"""
Collect fundamental data using Alpha Vantage OVERVIEW endpoint.
Saves CSV to ml/data/raw_stock_data.csv
"""
import os
import time
import csv
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

API_KEY = os.getenv('alphavantage_api_key')
if not API_KEY:
    print('alphavantage_api_key not set in environment')
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_CSV = DATA_DIR / 'raw_stock_data.csv'
TICKERS_FILE = ROOT / 'tickers.txt'

BASE_URL = 'https://www.alphavantage.co/query'

def fetch_overview(symbol: str):
    params = {'function': 'OVERVIEW', 'symbol': symbol, 'apikey': API_KEY}
    try:
        r = requests.get(BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data or 'Symbol' not in data:
            print(f'No overview data for {symbol}: {data}')
            return None
        return data
    except Exception as e:
        print(f'Error fetching overview for {symbol}: {e}')
        return None

def main():
    tickers = []
    with open(TICKERS_FILE, 'r') as f:
        for line in f:
            t = line.strip()
            if t:
                tickers.append(t)

    fieldnames = None
    rows = []
    for i, t in enumerate(tickers):
        print(f'Fetching {t} ({i+1}/{len(tickers)})')
        data = fetch_overview(t)
        if data:
            rows.append(data)
            if fieldnames is None:
                fieldnames = list(data.keys())
        # Respect rate limit (12s recommended for premium)
        time.sleep(12)

    if not rows:
        print('No data collected')
        return

    # ensure certain fields exist; write CSV
    if fieldnames is None:
        fieldnames = sorted({k for r in rows for k in r.keys()})

    with open(RAW_CSV, 'w', newline='', encoding='utf8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: (v if v is not None else '') for k, v in r.items()})

    print(f'Wrote {len(rows)} rows to {RAW_CSV}')

if __name__ == '__main__':
    main()
