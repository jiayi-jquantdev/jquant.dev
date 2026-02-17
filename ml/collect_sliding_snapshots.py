#!/usr/bin/env python3
"""Generate sliding 6-month snapshots for a universe of tickers.

For each ticker the script fetches monthly adjusted prices from AlphaVantage
and creates a snapshot for every month where a price 6 months ahead exists.
Each snapshot includes price_at_snapshot, price_plus_6m and forward_6m_return.
Optionally the script also fetches `OVERVIEW` to include `Sector` and `MarketCapitalization`.

Usage:
  python3 ml/collect_sliding_snapshots.py --tickers ml/tickers_5000.txt --out ml/data/historical_snapshots_5000_sliding.csv

Note: Requires `ALPHAVANTAGE_API_KEY` in environment. Rate-limits via `--rl_sleep` (seconds).
"""
import os
import sys
import time
import csv
import argparse
from datetime import datetime
import requests

API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY')


def fetch_monthly_prices(session, symbol, apikey, rl_sleep=0.2, retries=2):
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'TIME_SERIES_MONTHLY_ADJUSTED', 'symbol': symbol, 'apikey': apikey}
    for attempt in range(retries):
        try:
            time.sleep(rl_sleep)
            r = session.get(url, params=params, timeout=30)
            if r.status_code != 200:
                continue
            data = r.json()
            ts = data.get('Monthly Adjusted Time Series') or data.get('Monthly Adjusted Time Series'.replace(' ', ''))
            if not ts:
                # some responses use a slightly different key or return an error message
                ts = data.get('Monthly Time Series')
            if not ts:
                return None
            # return sorted list of (date_str, adj_close) ascending
            items = sorted(ts.items(), key=lambda x: x[0])
            out = [(d, float(vals.get('5. adjusted close') or vals.get('4. close'))) for d, vals in items]
            return out
        except Exception:
            time.sleep(1 + attempt)
    return None


def fetch_overview(session, symbol, apikey, rl_sleep=0.2, retries=2):
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'OVERVIEW', 'symbol': symbol, 'apikey': apikey}
    for attempt in range(retries):
        try:
            time.sleep(rl_sleep)
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception:
            time.sleep(1 + attempt)
    return {}


def build_snapshots_for_symbol(session, symbol, apikey, rl_sleep=0.2):
    prices = fetch_monthly_prices(session, symbol, apikey, rl_sleep=rl_sleep)
    if not prices or len(prices) < 7:
        return []
    # prices is list of (date_str, adj_close) ascending
    snapshots = []
    for i in range(len(prices) - 6):
        date_t, price_t = prices[i]
        date_t6, price_t6 = prices[i + 6]
        try:
            forward = (price_t6 / price_t) - 1.0
        except Exception:
            continue
        snapshots.append({'symbol': symbol, 'snapshot_date': date_t, 'price_at_snapshot': price_t, 'price_plus_6m': price_t6, 'forward_6m_return': forward})
    return snapshots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', required=True)
    parser.add_argument('--out', default='ml/data/historical_snapshots_5000_sliding.csv')
    parser.add_argument('--rl_sleep', type=float, default=0.2)
    parser.add_argument('--include_overview', action='store_true')
    args = parser.parse_args()

    if not API_KEY:
        print('Missing ALPHAVANTAGE_API_KEY in environment', file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.tickers):
        print(f'Ticker file not found: {args.tickers}', file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    session = requests.Session()

    fieldnames = ['symbol', 'snapshot_date', 'price_at_snapshot', 'price_plus_6m', 'forward_6m_return', 'sector', 'market_cap', 'pe_ratio']
    with open(args.out, 'w', newline='') as outf:
        writer = csv.DictWriter(outf, fieldnames=fieldnames)
        writer.writeheader()

        with open(args.tickers) as f:
            tickers = [l.strip() for l in f if l.strip()]

        total = len(tickers)
        for idx, sym in enumerate(tickers, 1):
            try:
                snapshots = build_snapshots_for_symbol(session, sym, API_KEY, rl_sleep=args.rl_sleep)
                if not snapshots:
                    if idx % 100 == 0:
                        print(f'[{idx}/{total}] {sym}: no snapshots')
                    continue
                overview = {}
                if args.include_overview:
                    overview = fetch_overview(session, sym, API_KEY, rl_sleep=args.rl_sleep) or {}
                sector = overview.get('Sector', '')
                market_cap = overview.get('MarketCapitalization', '')
                pe = overview.get('PERatio', '')

                for s in snapshots:
                    row = {
                        'symbol': s['symbol'],
                        'snapshot_date': s['snapshot_date'],
                        'price_at_snapshot': s['price_at_snapshot'],
                        'price_plus_6m': s['price_plus_6m'],
                        'forward_6m_return': s['forward_6m_return'],
                        'sector': sector,
                        'market_cap': market_cap,
                        'pe_ratio': pe,
                    }
                    writer.writerow(row)

                if idx % 100 == 0:
                    print(f'[{idx}/{total}] {sym}: wrote {len(snapshots)} snapshots')
            except KeyboardInterrupt:
                print('Interrupted by user', file=sys.stderr)
                return
            except Exception as e:
                print(f'Error processing {sym}: {e}', file=sys.stderr)


if __name__ == '__main__':
    main()
