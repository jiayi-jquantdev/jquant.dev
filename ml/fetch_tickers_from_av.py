#!/usr/bin/env python3
"""Fetch listing from AlphaVantage (LISTING_STATUS) and write top 5000 tickers to data/tickers_5000.txt
Requires ALPHAVANTAGE_API_KEY in env or .env file. Will prefer env var.
"""
import os
import requests
import csv

API_URL = 'https://www.alphavantage.co/query'

def read_env_key():
    key = os.environ.get('ALPHAVANTAGE_API_KEY')
    if key:
        return key
    # try .env
    envfile = '.env'
    if os.path.exists(envfile):
        with open(envfile) as f:
            for line in f:
                line = line.strip()
                if line.startswith('ALPHAVANTAGE_API_KEY'):
                    parts = line.split('=',1)
                    if len(parts)>1:
                        return parts[1].strip().strip('"').strip("'")
    return None


def fetch_listing(apikey):
    params = {'function':'LISTING_STATUS','apikey':apikey}
    r = requests.get(API_URL, params=params, timeout=60)
    r.raise_for_status()
    text = r.text
    return text


def parse_csv(text):
    lines = text.splitlines()
    reader = csv.DictReader(lines)
    symbols = []
    for row in reader:
        sym = row.get('symbol') or row.get('ticker') or row.get('Symbol')
        if sym:
            symbols.append(sym.strip())
    return symbols


def main():
    apikey = read_env_key()
    if not apikey:
        raise SystemExit('ALPHAVANTAGE_API_KEY not set in env or .env')
    print('fetching listing_status...')
    text = fetch_listing(apikey)
    syms = parse_csv(text)
    print('got', len(syms), 'symbols')
    # dedupe while preserving order
    seen = set()
    out = []
    for s in syms:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    N = min(5000, len(out))
    os.makedirs('data', exist_ok=True)
    with open('data/tickers_5000.txt','w') as f:
        for s in out[:N]:
            f.write(s + '\n')
    print('wrote', N, 'tickers to data/tickers_5000.txt')

if __name__ == '__main__':
    main()
