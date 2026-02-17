#!/usr/bin/env python3
"""Force re-fetch AlphaVantage endpoints for tickers present in cache.

Writes to `ml/cache/{kind}_{ticker}.json` and overwrites existing files.
Usage: python3 ml/fetch_all_endpoints_force.py --apikey KEY --rate 0.05
"""
import os
import time
import json
import argparse
from glob import glob
import requests

CACHE_DIR = 'ml/cache'
AV_ENDPOINT = 'https://www.alphavantage.co/query'

def tickers_from_cache():
    # prefer overview files; fallback to any *_<TICKER>.json
    pats = glob(os.path.join(CACHE_DIR, 'overview_*.json'))
    if pats:
        return [os.path.basename(p).replace('overview_','').replace('.json','') for p in pats]
    # fallback
    pats = glob(os.path.join(CACHE_DIR, '*_*.json'))
    out = set()
    for p in pats:
        name = os.path.basename(p)
        try:
            kind, tick = name.split('_',1)
            tick = tick.rsplit('.json',1)[0]
            out.add(tick)
        except Exception:
            continue
    return sorted(out)

def fetch_and_cache(kind, ticker, apikey, rate):
    func_map = {
        'income': 'INCOME_STATEMENT',
        'balance': 'BALANCE_SHEET',
        'cashflow': 'CASH_FLOW',
        'earnings': 'EARNINGS',
        'overview': 'OVERVIEW'
    }
    func = func_map.get(kind)
    if not func:
        return False
    params = {'function': func, 'symbol': ticker, 'apikey': apikey}
    for attempt in range(3):
        try:
            r = requests.get(AV_ENDPOINT, params=params, timeout=30)
            if r.status_code == 200:
                data = r.json()
                p = os.path.join(CACHE_DIR, f'{kind}_{ticker}.json')
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
                return True
        except Exception:
            pass
        time.sleep(1 + attempt)
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apikey', required=True)
    parser.add_argument('--rate', type=float, default=0.05)
    parser.add_argument('--tickers-file', default=None)
    args = parser.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)

    if args.tickers_file and os.path.exists(args.tickers_file):
        with open(args.tickers_file) as f:
            tickers = [l.strip() for l in f if l.strip()]
    else:
        tickers = tickers_from_cache()

    kinds = ['income','balance','cashflow','earnings','overview']
    total = len(tickers) * len(kinds)
    print(f'Will fetch {total} endpoint calls for {len(tickers)} tickers')
    done = 0
    for i,t in enumerate(tickers,1):
        for k in kinds:
            ok = fetch_and_cache(k, t, args.apikey, args.rate)
            done += 1
            print(f'[{done}/{total}] {t} {k} ->', 'OK' if ok else 'FAIL')
            time.sleep(args.rate)
    print('Done')

if __name__ == '__main__':
    main()
