#!/usr/bin/env python3
"""
Calculate 6-month returns using Alpha Vantage TIME_SERIES_DAILY.
For each ticker in raw_stock_data.csv it fetches daily prices and computes
the percent change between the latest close and the close ~126 trading days ago
(~6 months). Writes ml/data/training_data.csv with fundamentals + return_6m.
"""
import os
import time
import csv
import requests
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

load_dotenv()

API_KEY = os.getenv('alphavantage_api_key')
if not API_KEY:
    print('alphavantage_api_key not set')
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_CSV = DATA_DIR / 'raw_stock_data.csv'
TRAIN_CSV = DATA_DIR / 'training_data.csv'

BASE_URL = 'https://www.alphavantage.co/query'

def fetch_daily(symbol: str):
    params = {'function': 'TIME_SERIES_DAILY', 'symbol': symbol, 'outputsize': 'full', 'apikey': API_KEY}
    try:
        r = requests.get(BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        ts = data.get('Time Series (Daily)') or data.get('Time Series (Daily)')
        if not ts:
            print(f'No time series for {symbol}: {data}')
            return None
        # convert to list of (date, close) sorted ascending by date
        items = sorted(((datetime.fromisoformat(d), float(v['4. close'])) for d, v in ts.items()), key=lambda x: x[0])
        return items
    except Exception as e:
        print(f'Error fetching daily for {symbol}: {e}')
        return None

def main():
    if not RAW_CSV.exists():
        print(f'{RAW_CSV} not found; run collect_data.py first')
        return

    with open(RAW_CSV, 'r', encoding='utf8') as f:
        reader = csv.DictReader(f)
        fundamentals = list(reader)

    out_rows = []
    for i, row in enumerate(fundamentals):
        symbol = row.get('Symbol') or row.get('symbol') or row.get('Ticker') or row.get('ticker')
        if not symbol:
            continue
        symbol = symbol.strip()
        print(f'Processing {symbol} ({i+1}/{len(fundamentals)})')
        ts = fetch_daily(symbol)
        if not ts or len(ts) < 10:
            print(f'Insufficient price data for {symbol}')
            time.sleep(12)
            continue

        # latest close and close ~126 trading days ago (~6 months)
        latest_date, latest_close = ts[-1]
        idx_6m = max(0, len(ts) - 126)
        close_6m_ago = ts[idx_6m][1]
        try:
            return_6m = (latest_close / close_6m_ago - 1.0) * 100.0
        except Exception:
            print(f'Error computing return for {symbol}')
            time.sleep(12)
            continue

        out = dict(row)
        out['return_6m'] = f'{return_6m:.4f}'
        out['latest_close'] = f'{latest_close:.4f}'
        out_rows.append(out)

        # respect rate limits
        time.sleep(12)

    if not out_rows:
        print('No training rows created')
        return

    # write training CSV
    fieldnames = sorted({k for r in out_rows for k in r.keys()})
    with open(TRAIN_CSV, 'w', newline='', encoding='utf8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)

    print(f'Wrote {len(out_rows)} rows to {TRAIN_CSV}')

if __name__ == '__main__':
    main()
