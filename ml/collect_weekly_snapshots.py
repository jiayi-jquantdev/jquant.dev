#!/usr/bin/env python3
"""Collect weekly snapshots: daily prices (TIME_SERIES_DAILY) + cached fundamentals.
- Respects ALPHAVANTAGE_API_KEY and ALPHAVANTAGE_RATE_LIMIT_SECONDS env vars.
- Produces CSV: ml/data/weekly_snapshots_<N>_sample.csv for dry-runs, and ml/data/weekly_snapshots.csv for full run.

This script supports a dry-run `--tickers-file` with a small list for validation.
"""
import os
import time
import csv
import json
import argparse
from datetime import datetime, timedelta
import pandas as pd
import requests

API_URL = 'https://www.alphavantage.co/query'

def load_tickers(path):
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]


def fetch_daily(symbol, apikey):
    params = {'function':'TIME_SERIES_DAILY_ADJUSTED','symbol':symbol,'outputsize':'full','apikey':apikey}
    r = requests.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers-file', default='data/tickers_sample.txt', help='file with one ticker per line')
    parser.add_argument('--out', default='ml/data/weekly_snapshots_sample.csv')
    parser.add_argument('--apikey', default=os.environ.get('ALPHAVANTAGE_API_KEY'))
    parser.add_argument('--rate', type=float, default=float(os.environ.get('ALPHAVANTAGE_RATE_LIMIT_SECONDS', '0.05')))
    parser.add_argument('--weeks-back', type=int, default=260)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--append', action='store_true', help='append to existing output and skip tickers already present')
    args = parser.parse_args()

    if not args.apikey:
        raise SystemExit('Set ALPHAVANTAGE_API_KEY env var or --apikey')

    tickers = load_tickers(args.tickers_file)
    # if append requested, remove tickers already present in output
    if args.append and os.path.exists(args.out):
        try:
            import pandas as _pd
            existing = _pd.read_csv(args.out)
            done = set(existing['ticker'].astype(str).unique())
            tickers = [t for t in tickers if t not in done]
            print(f'Append mode: skipping {len(done)} completed tickers, {len(tickers)} remaining')
        except Exception as e:
            print('Append mode: failed to read existing output, proceeding with full list', e)
    rows = []
    # support per-ticker checkpointing to avoid losing work on interruption
    checkpoint_interval = 1
    for i, t in enumerate(tickers):
        try:
            data = fetch_daily(t, args.apikey)
        except Exception as e:
            print('fetch error', t, e)
            time.sleep(args.rate)
            continue
        # parse daily series
        ts = data.get('Time Series (Daily)') or data.get('Time Series (Daily)')
        if not ts:
            print('no daily series for', t)
            time.sleep(args.rate)
            continue
        dates = sorted(ts.keys())
        # load cached fundamentals if available
        fund_path = f'ml/cache/{t}_overview.json'
        fundamentals = {}
        if os.path.exists(fund_path):
            with open(fund_path) as f:
                fundamentals = json.load(f)
        # generate weekly snapshots: every Monday (or first trading day of week)
        # iterate weeks back from most recent date
        last_date = datetime.strptime(dates[-1], '%Y-%m-%d')
        for w in range(args.weeks_back):
            target = last_date - timedelta(weeks=w)
            # find first trading day on or after Monday of that week
            monday = target - timedelta(days=target.weekday())
            # find nearest trading day >= monday
            cand = None
            for d in dates:
                d_dt = datetime.strptime(d, '%Y-%m-%d')
                if d_dt >= monday:
                    cand = d
                    break
            if not cand:
                continue
            # price six months later
            try:
                sixmo_dt = datetime.strptime(cand, '%Y-%m-%d') + timedelta(days=182)
                sixmo_str = sixmo_dt.strftime('%Y-%m-%d')
                # find nearest trading day >= sixmo_str
                six_cand = None
                for d in dates:
                    if datetime.strptime(d, '%Y-%m-%d') >= sixmo_dt:
                        six_cand = d
                        break
                if not six_cand:
                    continue
                price_at = float(ts[cand]['4. close'])
                price_6m = float(ts[six_cand]['4. close'])
                ret6 = (price_6m - price_at) / price_at
            except Exception:
                continue
            row = {
                'ticker': t,
                'snapshot_date': cand,
                'price_at_snapshot': price_at,
                'price_6m': price_6m,
                'forward_6m_return': ret6,
            }
            # attach any top-level cached fundamentals (OVERVIEW keys)
            for k,v in (fundamentals.items() if isinstance(fundamentals, dict) else [] ):
                # only attach simple scalar overview fields
                if isinstance(v, (str,int,float)):
                    row[f'overview_{k}'] = v
            rows.append(row)
        # after finishing this ticker, flush its rows to disk to checkpoint progress
        try:
            import pandas as _pd
            ticker_df = _pd.DataFrame(rows[-5000:]) if len(rows)>0 else _pd.DataFrame()
            if not ticker_df.empty:
                write_header = not os.path.exists(args.out)
                ticker_df.to_csv(args.out, mode='a', header=write_header, index=False)
        except Exception as e:
            print('checkpoint write failed for', t, e)
        print(f'collected {len(rows)} rows so far (ticker {i+1}/{len(tickers)})')
        time.sleep(args.rate)
        if args.dry_run and i>=9:
            break

    # Final summary: if we didn't flush (small runs), ensure file exists
    try:
        import pandas as _pd
        if len(rows)>0 and not os.path.exists(args.out):
            _pd.DataFrame(rows).to_csv(args.out, index=False)
        print('final rows collected:', len(rows))
    except Exception as e:
        print('final write check failed', e)

if __name__ == '__main__':
    main()
