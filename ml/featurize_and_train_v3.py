#!/usr/bin/env python3
"""Featurize existing snapshots with valuation and momentum features and retrain.

Produces `ml/data/historical_snapshots_1000_v3.csv` and `ml/models/snapshot_xgb_v3.pkl`.

Features implemented:
 - P/E (price / TTM EPS) using AlphaVantage `EARNINGS` per ticker (cached)
 - P/B using (totalAssets - totalLiabilities) / sharesOutstanding from `OVERVIEW` (cached)
 - P/E vs sector median, P/B vs sector median
 - P/E vs stock mean P/E (historical)
 - Momentum: 1m,3m,6m,12m returns computed from snapshot price series
 - Relative strength vs sector (6m)
 - Price vs 10-month rolling mean (proxy for 200-day MA)

Notes:
 - Requires `ALPHAVANTAGE_API_KEY` in env for earnings/overview fetches.
 - Caches API responses in `ml/cache/` to avoid repeat calls.
"""
import os
import sys
import time
import json
import argparse
from datetime import datetime
import numpy as np
import pandas as pd
import requests
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
import joblib

API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY')
CACHE_DIR = 'ml/cache'


def ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def fetch_cached(session, url, params, cache_path, rl_sleep=0.25, retries=3):
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    for attempt in range(retries):
        try:
            time.sleep(rl_sleep)
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                data = r.json()
                with open(cache_path, 'w') as f:
                    json.dump(data, f)
                return data
        except Exception:
            time.sleep(1 + attempt)
    return None


def get_earnings(session, symbol):
    cache = os.path.join(CACHE_DIR, f'earnings_{symbol}.json')
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'EARNINGS', 'symbol': symbol, 'apikey': API_KEY}
    return fetch_cached(session, url, params, cache)


def get_overview(session, symbol):
    cache = os.path.join(CACHE_DIR, f'overview_{symbol}.json')
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'OVERVIEW', 'symbol': symbol, 'apikey': API_KEY}
    return fetch_cached(session, url, params, cache)


def get_income_statement(session, symbol):
    cache = os.path.join(CACHE_DIR, f'income_{symbol}.json')
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'INCOME_STATEMENT', 'symbol': symbol, 'apikey': API_KEY}
    return fetch_cached(session, url, params, cache)


def get_balance_sheet(session, symbol):
    cache = os.path.join(CACHE_DIR, f'balance_{symbol}.json')
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'BALANCE_SHEET', 'symbol': symbol, 'apikey': API_KEY}
    return fetch_cached(session, url, params, cache)


def compute_eps_ttm_from_earnings(earnings_json, snapshot_date):
    # earnings_json contains 'quarterlyEarnings' with 'reportedDate' and 'reportedEPS'
    try:
        quarters = earnings_json.get('quarterlyEarnings', [])
        # keep quarters with date <= snapshot_date
        eps_list = []
        for q in quarters:
            d = q.get('reportedDate')
            if not d:
                continue
            if d <= snapshot_date:
                try:
                    eps = float(q.get('reportedEPS', 'nan'))
                    eps_list.append((d, eps))
                except Exception:
                    continue
        # sort descending date and take most recent four
        eps_list = sorted(eps_list, key=lambda x: x[0], reverse=True)
        ttm_eps = sum([e for _, e in eps_list[:4]]) if len(eps_list) >= 1 else None
        return ttm_eps
    except Exception:
        return None


def featurize(df, rl_sleep=0.25):
    session = requests.Session()
    ensure_cache()

    # momentum features: compute per-symbol price series and shifted returns
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
    df = df.sort_values(['ticker', 'snapshot_date']).reset_index(drop=True)
    # group price series
    for window, steps in [('r1m', 1), ('r3m', 3), ('r6m', 6), ('r12m', 12)]:
        df[window] = df.groupby('ticker')['price_at_snapshot'].transform(lambda s: s.pct_change(periods=steps))

    # rolling mean approx for 200-day -> use 10-month (~10 periods)
    df['ma_10m'] = df.groupby('ticker')['price_at_snapshot'].transform(lambda s: s.rolling(window=10, min_periods=1).mean())
    df['price_vs_ma10'] = df['price_at_snapshot'] / df['ma_10m']

    # per-ticker earnings and overview
    tickers = df['ticker'].unique()
    eps_map = {}
    shares_map = {}

    # maps to store fetched responses
    earnings_map = {}
    overview_map = {}
    income_map = {}
    balance_map = {}

    for i, t in enumerate(tickers, 1):
        try:
            e = get_earnings(session, t)
            o = get_overview(session, t)
            inc = get_income_statement(session, t)
            bal = get_balance_sheet(session, t)
            shares = None
            if o:
                try:
                    shares = float(o.get('SharesOutstanding') or o.get('SharesOutstanding'.lower()) or 0)
                except Exception:
                    shares = None
            eps_map[t] = e
            shares_map[t] = shares
            earnings_map[t] = e
            overview_map[t] = o
            income_map[t] = inc
            balance_map[t] = bal
            if i % 100 == 0:
                print(f'Fetched {i}/{len(tickers)} overviews/earnings/income/balance')
        except Exception as ex:
            print(f'Error fetching {t}: {ex}', file=sys.stderr)

    # compute eps_ttm per row
    def _eps_ttm(row):
        sym = row['ticker']
        ej = eps_map.get(sym)
        if not ej:
            return np.nan
        return compute_eps_ttm_from_earnings(ej, row['snapshot_date'].strftime('%Y-%m-%d'))

    df['eps_ttm'] = df.apply(_eps_ttm, axis=1)
    df['pe'] = df.apply(lambda r: (r['price_at_snapshot'] / r['eps_ttm']) if r['eps_ttm'] not in (None, 0, 0.0, np.nan) and not pd.isna(r['eps_ttm']) else np.nan, axis=1)

    # P/B using shares outstanding from overview and book value from snapshot
    def _pb(row):
        s = shares_map.get(row['ticker'])
        if not s or s == 0:
            return np.nan
        try:
            bv = (float(row.get('totalAssets', np.nan)) - float(row.get('totalLiabilities', np.nan))) / s
            return row['price_at_snapshot'] / bv if bv not in (0, None, np.nan) else np.nan
        except Exception:
            return np.nan

    df['pb'] = df.apply(_pb, axis=1)

    # sector medians per snapshot_date: compute median pe and pb for sector-date groups
    df['sector'] = df['sector'].fillna('')
    df['pe_sector_median'] = df.groupby(['snapshot_date', 'sector'])['pe'].transform('median')
    df['pb_sector_median'] = df.groupby(['snapshot_date', 'sector'])['pb'].transform('median')
    df['pe_vs_sector'] = df['pe'] / df['pe_sector_median']
    df['pb_vs_sector'] = df['pb'] / df['pb_sector_median']

    # per-stock historical average P/E (use mean over available history excluding current row)
    df['pe_mean_by_stock'] = df.groupby('ticker')['pe'].transform(lambda s: s.expanding().mean())
    df['pe_vs_hist_mean'] = df['pe'] / df['pe_mean_by_stock']

    # relative strength vs sector for 6m return
    df['r6m_sector_median'] = df.groupby(['snapshot_date', 'sector'])['r6m'].transform('median')
    df['r6m_vs_sector'] = df['r6m'] - df['r6m_sector_median']

    # clip extreme values
    numcols = ['pe', 'pb', 'pe_vs_sector', 'pb_vs_sector', 'pe_vs_hist_mean', 'r1m', 'r3m', 'r6m', 'r12m', 'price_vs_ma10', 'r6m_vs_sector']
    for c in numcols:
        if c in df.columns:
            # attach overview fields to df where available
            def _attach_overview(row):
                o = overview_map.get(row['ticker']) or {}
                out = {}
                keys = ['PERatio','PriceToBookRatio','PriceToSalesRatio','EVToRevenue','EVToEBITDA','PEGRatio','ForwardPE','ProfitMargin','OperatingMarginTTM','ReturnOnAssetsTTM','ReturnOnEquityTTM','EPS','BookValue','RevenuePerShareTTM','DividendPerShare','Beta','52WeekHigh','52WeekLow','50DayMovingAverage','200DayMovingAverage','AnalystTargetPrice','DividendDate','ExDividendDate']
                for k in keys:
                    v = o.get(k) or o.get(k.lower()) or o.get(k.replace('TTM',''), None)
                    out[k] = v
                return pd.Series(out)

            try:
                ov_df = df.apply(_attach_overview, axis=1)
                for c in ov_df.columns:
                    df[c] = ov_df[c]
            except Exception:
                pass

            # parse earnings quarterly details for surprises and trends
            def _attach_earnings(row):
                ej = earnings_map.get(row['ticker']) or {}
                quarters = ej.get('quarterlyEarnings', []) if isinstance(ej, dict) else []
                snap = row['snapshot_date'].strftime('%Y-%m-%d')
                filtered = [q for q in quarters if q.get('reportedDate') and q.get('reportedDate') <= snap]
                filtered = sorted(filtered, key=lambda x: x.get('reportedDate', ''), reverse=True)[:8]
                out = {}
                for i, q in enumerate(filtered):
                    out[f'rep_eps_q{i+1}'] = q.get('reportedEPS')
                    out[f'est_eps_q{i+1}'] = q.get('estimatedEPS')
                    try:
                        out[f'surprise_q{i+1}'] = float(q.get('reportedEPS')) - float(q.get('estimatedEPS')) if q.get('reportedEPS') and q.get('estimatedEPS') else None
                    except Exception:
                        out[f'surprise_q{i+1}'] = None
                    out[f'surprise_pct_q{i+1}'] = q.get('surprisePercentage')
                beats = 0
                for q in filtered:
                    try:
                        if float(q.get('reportedEPS')) > float(q.get('estimatedEPS')):
                            beats += 1
                    except Exception:
                        pass
                out['earnings_beats_ratio'] = beats / len(filtered) if filtered else None
                try:
                    sp = [float(q.get('surprisePercentage').strip('%')) for q in filtered if q.get('surprisePercentage')]
                    out['earnings_avg_surprise_pct'] = sum(sp)/len(sp) if sp else None
                except Exception:
                    out['earnings_avg_surprise_pct'] = None
                return pd.Series(out)

            try:
                earn_df = df.apply(_attach_earnings, axis=1)
                for c in earn_df.columns:
                    df[c] = earn_df[c]
            except Exception:
                pass

            # attach income statement and balance sheet quarterly fields
            def _select_latest_report(reports, snap_date):
                if not reports:
                    return None
                candidates = [r for r in reports if r.get('fiscalDateEnding') and r.get('fiscalDateEnding') <= snap_date]
                if not candidates:
                    return reports[0]
                candidates = sorted(candidates, key=lambda x: x.get('fiscalDateEnding'), reverse=True)
                return candidates[0]

            def _attach_income(row):
                inc = income_map.get(row['ticker']) or {}
                reports = inc.get('quarterlyReports', []) if isinstance(inc, dict) else []
                rep = _select_latest_report(reports, row['snapshot_date'].strftime('%Y-%m-%d'))
                out = {}
                if rep:
                    keys = {'grossProfit':'grossProfit','operatingIncome':'operatingIncome','ebitda':'ebitda','interestExpense':'interestExpense','incomeTaxExpense':'incomeTaxExpense','researchAndDevelopment':'researchAndDevelopment','sellingGeneralAndAdministrative':'sellingGeneralAndAdministrative','totalRevenue':'totalRevenue','netIncome':'netIncome'}
                    for k,v in keys.items():
                        out[k] = rep.get(v)
                    try:
                        tr = float(rep.get('totalRevenue') or 0)
                        out['gross_margin'] = float(rep.get('grossProfit'))/tr if tr and rep.get('grossProfit') else None
                        out['operating_margin'] = float(rep.get('operatingIncome'))/tr if tr and rep.get('operatingIncome') else None
                        out['ebitda_margin'] = float(rep.get('ebitda'))/tr if tr and rep.get('ebitda') else None
                    except Exception:
                        out['gross_margin']=out['operating_margin']=out['ebitda_margin']=None
                return pd.Series(out)

            def _attach_balance(row):
                bal = balance_map.get(row['ticker']) or {}
                reports = bal.get('quarterlyReports', []) if isinstance(bal, dict) else []
                rep = _select_latest_report(reports, row['snapshot_date'].strftime('%Y-%m-%d'))
                out = {}
                if rep:
                    keys = {'totalCurrentAssets':'currentAssets','totalCurrentLiabilities':'currentLiabilities','inventory':'inventory','currentNetReceivables':'accountsReceivable','totalShareholderEquity':'shareholderEquity','longTermDebt':'longTermDebt','shortTermDebt':'shortTermDebt','goodwill':'goodwill','intangibleAssets':'intangibleAssets'}
                    for k,v in keys.items():
                        out[v] = rep.get(k)
                    try:
                        ca = float(rep.get('totalCurrentAssets') or 0)
                        cl = float(rep.get('totalCurrentLiabilities') or 0)
                        inv = float(rep.get('inventory') or 0)
                        out['current_ratio'] = ca / cl if cl else None
                        out['quick_ratio'] = (ca - inv) / cl if cl else None
                        ld = float(rep.get('longTermDebt') or 0)
                        sd = float(rep.get('shortTermDebt') or 0)
                        eq = float(rep.get('totalShareholderEquity') or 0)
                        out['debt_to_equity'] = (ld + sd) / eq if eq else None
                    except Exception:
                        out['current_ratio']=out['quick_ratio']=out['debt_to_equity']=None
                return pd.Series(out)

            try:
                inc_df = df.apply(_attach_income, axis=1)
                for c in inc_df.columns:
                    df[c] = inc_df[c]
            except Exception:
                pass

            try:
                bal_df = df.apply(_attach_balance, axis=1)
                for c in bal_df.columns:
                    df[c] = bal_df[c]
            except Exception:
                pass
