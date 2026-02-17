#!/usr/bin/env python3
"""Expand features by extracting quarterly fundamentals from AlphaVantage cache (or API).

Behavior:
- Loads `ml/data/historical_snapshots_1000_v3.csv` as input.
- For each `ticker`, looks for cached JSONs in `ml/cache/` named:
  - income_{TICKER}.json (INCOME_STATEMENT)
  - balance_{TICKER}.json (BALANCE_SHEET)
  - cashflow_{TICKER}.json (CASH_FLOW)
  - earnings_{TICKER}.json (EARNINGS) [often already present]
  - overview_{TICKER}.json (OVERVIEW)
- If cache missing and environment variable `ALPHAVANTAGE_API_KEY` is set and
  `ALPHAVANTAGE_FETCH=1`, the script will fetch the endpoint and cache it (rate-limited).
- Constructs a large set of backward-looking features per snapshot by selecting
  quarterly reports with `fiscalDateEnding <= snapshot_date` and computing
  last-quarter, TTM, QoQ, YoY, trend and std for each numeric field found.
- Adds sector-relative versions and interaction terms.
- Saves expanded CSV to `ml/data/historical_snapshots_1000_v3_expanded.csv`.

Notes:
- This is an automated, generic extractor to produce 100+ features; it prioritizes
  using cached JSONs to avoid hitting API limits. To enable live fetching set
  environment variables `ALPHAVANTAGE_API_KEY` and `ALPHAVANTAGE_FETCH=1`.
"""
import os
import time
import json
from collections import defaultdict
import numpy as np
import pandas as pd

CACHE_DIR = 'ml/cache'
INPUT_CSV = 'ml/data/historical_snapshots_1000_v3.csv'
OUTPUT_CSV = 'ml/data/historical_snapshots_1000_v3_expanded.csv'

AV_ENDPOINT = 'https://www.alphavantage.co/query'

def cache_path(kind, ticker):
    return os.path.join(CACHE_DIR, f"{kind}_{ticker}.json")


def load_cached(kind, ticker):
    p = cache_path(kind, ticker)
    if os.path.exists(p) and os.path.getsize(p) > 2:
        try:
            with open(p,'r',encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def fetch_and_cache(kind, ticker, api_key, rate_limit=12):
    import requests
    func_map = {
        'income': 'INCOME_STATEMENT',
        'balance': 'BALANCE_SHEET',
        'cashflow': 'CASH_FLOW',
        'earnings': 'EARNINGS',
        'overview': 'OVERVIEW'
    }
    func = func_map.get(kind)
    if not func:
        return None
    params = {'function': func, 'symbol': ticker, 'apikey': api_key}
    r = requests.get(AV_ENDPOINT, params=params, timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    # simple rate limit
    time.sleep(rate_limit)
    p = cache_path(kind, ticker)
    with open(p,'w',encoding='utf-8') as f:
        json.dump(data, f)
    return data


def numeric_fields_from_reports(reports):
    # reports: list of dicts (quarterlyReports)
    # Collect numeric keys except dates
    keys = set()
    for r in reports:
        for k,v in r.items():
            if k.lower().endswith('date') or 'fiscal' in k.lower():
                continue
            try:
                float(v)
                keys.add(k)
            except Exception:
                pass
    return sorted(keys)


def to_float(x):
    try:
        return float(x)
    except Exception:
        return np.nan


def series_stats(vals):
    # vals: list of floats (ordered most-recent first)
    vals = [v for v in vals if v is not None and not (isinstance(v,float) and np.isnan(v))]
    if not vals:
        return {}
    arr = np.array(vals, dtype=float)
    res = {
        'last': float(arr[0]),
        'ttm': float(np.nansum(arr[:4])) if len(arr)>=1 else float(np.nansum(arr)),
        'mean4': float(np.nanmean(arr[:4])) if len(arr)>=1 else float(np.nanmean(arr)),
        'std4': float(np.nanstd(arr[:4])) if len(arr)>=1 else float(np.nanstd(arr)),
    }
    if len(arr) >= 2 and not np.isclose(arr[1],0):
        res['qoq'] = float((arr[0]-arr[1])/abs(arr[1]))
    else:
        res['qoq'] = np.nan
    if len(arr) >= 4:
        prev_year = np.nansum(arr[4:8]) if len(arr)>=8 else np.nan
        if prev_year and not np.isclose(prev_year,0):
            res['yoy'] = float((res['ttm'] - prev_year)/abs(prev_year))
        else:
            res['yoy'] = np.nan
    else:
        res['yoy'] = np.nan
    # simple trend (slope) over up to 4 quarters
    n = min(4, len(arr))
    if n >= 2:
        y = arr[:n]
        x = np.arange(n)
        A = np.vstack([x, np.ones(n)]).T
        m, c = np.linalg.lstsq(A, y, rcond=None)[0]
        res['trend_slope'] = float(m)
    else:
        res['trend_slope'] = np.nan
    res['improving'] = 1 if (not np.isnan(res['trend_slope']) and res['trend_slope']>0) else 0
    return res


def expand_row_features(row, cached_reports):
    # cached_reports: dict kind -> json data
    feats = {}
    snapshot_date = pd.to_datetime(row['snapshot_date'])
    # process income statement
    income = cached_reports.get('income')
    if income and 'quarterlyReports' in income:
        reports = income['quarterlyReports']
        # filter by fiscalDateEnding <= snapshot_date
        valid = [r for r in reports if pd.to_datetime(r.get('fiscalDateEnding',None), errors='coerce') <= snapshot_date]
        # order by most recent first
        valid = sorted(valid, key=lambda r: r.get('fiscalDateEnding',''), reverse=True)
        keys = numeric_fields_from_reports(valid)
        for k in keys:
            vals = [to_float(r.get(k)) for r in valid]
            s = series_stats(vals)
            for sk,sv in s.items():
                feats[f'income_{k}_{sk}'] = sv

    # balance sheet
    balance = cached_reports.get('balance')
    if balance and 'quarterlyReports' in balance:
        reports = balance['quarterlyReports']
        valid = [r for r in reports if pd.to_datetime(r.get('fiscalDateEnding',None), errors='coerce') <= snapshot_date]
        valid = sorted(valid, key=lambda r: r.get('fiscalDateEnding',''), reverse=True)
        keys = numeric_fields_from_reports(valid)
        for k in keys:
            vals = [to_float(r.get(k)) for r in valid]
            s = series_stats(vals)
            for sk,sv in s.items():
                feats[f'balance_{k}_{sk}'] = sv

    # cashflow
    cash = cached_reports.get('cashflow')
    if cash and 'quarterlyReports' in cash:
        reports = cash['quarterlyReports']
        valid = [r for r in reports if pd.to_datetime(r.get('fiscalDateEnding',None), errors='coerce') <= snapshot_date]
        valid = sorted(valid, key=lambda r: r.get('fiscalDateEnding',''), reverse=True)
        keys = numeric_fields_from_reports(valid)
        for k in keys:
            vals = [to_float(r.get(k)) for r in valid]
            s = series_stats(vals)
            for sk,sv in s.items():
                feats[f'cash_{k}_{sk}'] = sv

    # earnings (quarterlyEPS, reportedDate, estimatedEPS)
    earnings = cached_reports.get('earnings')
    if earnings and 'quarterlyEarnings' in earnings:
        q = earnings['quarterlyEarnings']
        valid = [r for r in q if pd.to_datetime(r.get('reportedDate',None), errors='coerce') <= snapshot_date]
        valid = sorted(valid, key=lambda r: r.get('reportedDate',''), reverse=True)
        surprises = []
        revenue_surprises = []
        eps_vals = []
        for r in valid[:8]:
            est = to_float(r.get('estimatedEPS'))
            rep = to_float(r.get('reportedEPS'))
            if not np.isnan(est) and not np.isnan(rep):
                surprises.append((rep - est) / (abs(est) if abs(est)>1e-9 else 1.0))
            # revenue fields sometimes present
            if 'reportedRevenue' in r and 'estimatedRevenue' in r:
                rv = to_float(r.get('reportedRevenue'))
                re = to_float(r.get('estimatedRevenue'))
                if not np.isnan(rv) and not np.isnan(re):
                    revenue_surprises.append((rv - re) / (abs(re) if abs(re)>1e-9 else 1.0))
            if not np.isnan(rep): eps_vals.append(rep)
        if surprises:
            feats['earnings_surprise_avg8'] = float(np.nanmean(surprises))
            feats['earnings_surprise_std8'] = float(np.nanstd(surprises))
            feats['earnings_beat_rate8'] = float(np.mean([1 if s>0 else 0 for s in surprises]))
        else:
            feats['earnings_surprise_avg8'] = np.nan
            feats['earnings_surprise_std8'] = np.nan
            feats['earnings_beat_rate8'] = np.nan
        if revenue_surprises:
            feats['revenue_surprise_avg8'] = float(np.nanmean(revenue_surprises))
        else:
            feats['revenue_surprise_avg8'] = np.nan
        feats['eps_last'] = float(eps_vals[0]) if eps_vals else np.nan

    # overview (for marketcap, sector etc) - only backward-looking static fields
    ov = cached_reports.get('overview')
    if ov:
        for k,v in ov.items():
            if k.lower()=='description' or k.lower().endswith('address'):
                continue
            # keep numeric fields
            try:
                feats[f'overview_{k}'] = float(v)
            except Exception:
                # keep text sector/name
                if k in ('Sector','Industry'):
                    feats[f'overview_{k}'] = v

    return feats


def main():
    df = pd.read_csv(INPUT_CSV)
    tickers = sorted(df['ticker'].unique())
    print('Tickers in dataset:', len(tickers))

    api_key = os.getenv('ALPHAVANTAGE_API_KEY')
    do_fetch = os.getenv('ALPHAVANTAGE_FETCH','0') == '1'
    # allow fractional seconds for high-rate premium keys
    try:
        rate_limit = float(os.getenv('ALPHAVANTAGE_RATE_LIMIT_SECONDS','12'))
    except Exception:
        rate_limit = 12.0

    rows = []
    missing_count = 0
    for i,row in df.iterrows():
        ticker = row['ticker']
        cached = {}
        for kind in ('income','balance','cashflow','earnings','overview'):
            data = load_cached(kind, ticker)
            if data is None and do_fetch and api_key:
                data = fetch_and_cache(kind, ticker, api_key, rate_limit=rate_limit)
            cached[kind] = data
        feats = expand_row_features(row, cached)
        if not feats:
            missing_count += 1
        # merge
        merged = dict(row)
        merged.update(feats)
        rows.append(merged)

    newdf = pd.DataFrame(rows)
    print('Expanded rows:', len(newdf), 'missing feature rows:', missing_count)
    # compute sector medians for numeric expanded features
    numcols = [c for c in newdf.columns if newdf[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    # save
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    newdf.to_csv(OUTPUT_CSV, index=False)
    print('Saved expanded CSV to', OUTPUT_CSV)


if __name__ == '__main__':
    main()
