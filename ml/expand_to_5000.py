#!/usr/bin/env python3
"""Build a 5,000-ticker universe using AlphaVantage LISTING_STATUS + OVERVIEW filtering.

Steps:
 - Download LISTING_STATUS CSV from AlphaVantage (function=LISTING_STATUS)
 - Keep rows with exchange in ("NYSE","NASDAQ") and status "Active"
 - For candidates, call OVERVIEW to get MarketCapitalization and select >= 100,000,000
 - Stop when we have target count (default 5000)
 - Write `ml/tickers_5000.txt`

If AlphaVantage listing fetch fails, falls back to existing `ml/exchange_symbols.txt`.
"""
import os
import sys
import time
import csv
import argparse
import requests

API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY')


def fetch_listing_status_csv(api_key, rl_wait=0.2):
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'LISTING_STATUS', 'apikey': api_key}
    try:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def parse_listing_text(text):
    # CSV with header Symbol,Exchange,AssetType,IPODate,DelistingDate,Status
    rows = []
    for i, line in enumerate(text.splitlines()):
        if i == 0:
            continue
        parts = [p.strip().strip('"') for p in line.split(',')]
        if len(parts) < 6:
            continue
        sym, exch, asset, ipo, delist, status = parts[:6]
        rows.append({'symbol': sym, 'exchange': exch, 'assetType': asset, 'status': status})
    return rows


def safe_overview(session, symbol, apikey, rl_sleep=0.2, retries=3):
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'OVERVIEW', 'symbol': symbol, 'apikey': apikey}
    for attempt in range(retries):
        try:
            time.sleep(rl_sleep)
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception:
            time.sleep(2 ** attempt)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=int, default=5000)
    parser.add_argument('--min_mcap', type=float, default=1e8)
    parser.add_argument('--out', default='ml/tickers_5000.txt')
    parser.add_argument('--rl_sleep', type=float, default=0.2)
    args = parser.parse_args()

    if not API_KEY:
        print('Missing ALPHAVANTAGE_API_KEY in environment', file=sys.stderr)
        sys.exit(1)

    text = fetch_listing_status_csv(API_KEY, rl_wait=args.rl_sleep)
    candidates = []
    if text:
        rows = parse_listing_text(text)
        for r in rows:
            exch = r.get('exchange','').upper()
            if exch in ('NYSE','NASDAQ') and r.get('status','').lower() == 'active':
                candidates.append(r['symbol'])
        print(f'Parsed {len(candidates)} exchange-active candidates from LISTING_STATUS')
    else:
        # fallback to existing exchange_symbols file
        fallback = 'ml/exchange_symbols.txt'
        if os.path.exists(fallback):
            with open(fallback) as f:
                candidates = [l.strip() for l in f if l.strip()]
            print(f'Fallback: loaded {len(candidates)} symbols from {fallback}')
        else:
            print('No listing_status and no fallback symbols; aborting', file=sys.stderr)
            sys.exit(1)

    session = requests.Session()
    winners = []
    for i, sym in enumerate(candidates, 1):
        if len(winners) >= args.target:
            break
        ov = safe_overview(session, sym, API_KEY, rl_sleep=args.rl_sleep)
        if not ov:
            continue
        mcap = ov.get('MarketCapitalization')
        try:
            mcap_v = float(mcap) if mcap not in (None, '') else 0.0
        except Exception:
            mcap_v = 0.0
        if mcap_v >= args.min_mcap:
            winners.append(sym)
        if i % 200 == 0:
            print(f'Checked {i} candidates, found {len(winners)} winners so far')

    print(f'Selected {len(winners)} symbols; writing to {args.out}')
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        for s in winners:
            f.write(s + '\n')


if __name__ == '__main__':
    main()
