#!/usr/bin/env python3
"""Collect historical quarterly snapshots per ticker using AlphaVantage.

Writes a CSV of snapshot rows with `snapshot_date`, `collection_date`, fundamentals,
`price_at_snapshot`, `price_+6m`, and `forward_6m_return`.
"""
import os
import sys
import time
import csv
import math
import argparse
from datetime import datetime, timedelta
import requests
from collections import defaultdict

API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")
# support either calls-per-minute (e.g. 300) or seconds-per-call (e.g. 0.2)
rate_env = os.environ.get("ALPHAVANTAGE_RATE_LIMIT_SECONDS")
if rate_env is None:
    CALLS_PER_MIN = 300
else:
    try:
        rate_val = float(rate_env)
        if rate_val < 1:
            # interpret as seconds per call
            CALLS_PER_MIN = max(1, int(round(60.0 / rate_val)))
        else:
            CALLS_PER_MIN = int(rate_val)
    except Exception:
        CALLS_PER_MIN = 300


class RateLimiter:
    def __init__(self, calls_per_minute: int):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / max(1, calls_per_minute)
        self._last = 0.0

    def wait(self):
        now = time.time()
        elapsed = now - self._last
        to_wait = self.min_interval - elapsed
        if to_wait > 0:
            time.sleep(to_wait)
        self._last = time.time()


def safe_get(session, url, params, rl: RateLimiter, max_retries=3):
    for attempt in range(max_retries):
        try:
            rl.wait()
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
        except Exception:
            time.sleep(2 ** attempt)
    return None


def parse_monthly_prices(monthly_json):
    # AlphaVantage returns a dict with key 'Monthly Adjusted' or 'Time Series (Monthly)'
    for k in ("Monthly Adjusted Time Series", "Monthly Adjusted", "Time Series (Monthly)"):
        if k in monthly_json:
            series = monthly_json[k]
            break
    else:
        # try common alternative
        keys = [k for k in monthly_json.keys() if k.lower().startswith("time series")]
        if keys:
            series = monthly_json[keys[0]]
        else:
            return {}
    # series: date -> {fields}
    parsed = {}
    for d, v in series.items():
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            continue
        # try adjusted close then close
        price = v.get("5. adjusted close") or v.get("4. close")
        try:
            parsed[dt] = float(price)
        except Exception:
            parsed[dt] = math.nan
    return parsed


def quarter_end_months(latest_date: datetime, periods=20):
    # return list of quarter-end dates (month end) descending
    dates = []
    cur = latest_date.replace(day=1)
    # move to last month
    cur = (cur + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    while len(dates) < periods:
        dates.append(cur)
        # step back approx 3 months
        back = cur - timedelta(days=75)
        cur = back.replace(day=1)
        cur = (cur + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    return dates


def nearest_price(prices: dict, target_date: datetime):
    # prices keys are datetimes; find latest date <= target_date
    candidates = [d for d in prices.keys() if d <= target_date]
    if not candidates:
        return math.nan, None
    d = max(candidates)
    return prices[d], d


def load_tickers(path, limit=None):
    with open(path) as f:
        tickers = [line.strip() for line in f if line.strip()]
    if limit:
        return tickers[:limit]
    return tickers


def collect_for_ticker(session, rl, ticker, endpoints):
    base = "https://www.alphavantage.co/query"
    results = {}
    # Overview (we'll include non-time-varying fields like Sector)
    overview = safe_get(session, base, {"function": "OVERVIEW", "symbol": ticker, "apikey": API_KEY}, rl)
    results["overview"] = overview or {}
    # Financial statements
    for fn in ("INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW", "EARNINGS"):
        j = safe_get(session, base, {"function": fn, "symbol": ticker, "apikey": API_KEY}, rl)
        results[fn.lower()] = j or {}
    # Monthly prices
    monthly = safe_get(session, base, {"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": ticker, "apikey": API_KEY}, rl)
    results["monthly"] = monthly or {}
    return results


def build_snapshots(ticker, data, max_quarters=20):
    monthly = parse_monthly_prices(data.get("monthly", {}))
    if not monthly:
        return []
    latest = max(monthly.keys())
    quarters = quarter_end_months(latest, periods=max_quarters)
    snapshots = []
    # prepare lookup for fundamentals: use quarterlyReports where possible
    income = data.get("income_statement", {})
    balance = data.get("balance_sheet", {})
    cash = data.get("cash_flow", {})
    earnings = data.get("earnings", {})

    def pick_field(reports, date, field):
        if not reports:
            return None
        reports_list = reports.get("quarterlyReports") or reports.get("quarterlyReports", [])
        if not isinstance(reports_list, list):
            return None
        # reports_list is list of dicts with fiscalDateEnding
        candidates = [r for r in reports_list if r.get("fiscalDateEnding") and datetime.strptime(r["fiscalDateEnding"], "%Y-%m-%d") <= date]
        if not candidates:
            return None
        best = max(candidates, key=lambda r: r.get("fiscalDateEnding"))
        return best.get(field)

    for qdate in quarters:
        row = {"ticker": ticker, "snapshot_date": qdate.strftime("%Y-%m-%d"), "collection_date": datetime.utcnow().strftime("%Y-%m-%d")}
        # fundamentals (example set)
        for field in ("totalRevenue", "netIncome", "totalAssets", "totalLiabilities", "operatingCashflow"):
            val = None
            if field in ("totalRevenue", "netIncome"):
                val = pick_field(income, qdate, field)
            elif field in ("totalAssets", "totalLiabilities"):
                val = pick_field(balance, qdate, field)
            elif field == "operatingCashflow":
                val = pick_field(cash, qdate, "operatingCashflow")
            try:
                row[field] = float(val) if val not in (None, "None", "") else math.nan
            except Exception:
                row[field] = math.nan
        # sector/static
        row["sector"] = data.get("overview", {}).get("Sector")
        # prices
        price_at, price_date = nearest_price(monthly, qdate)
        # price 6 months later
        six_month_date = qdate + timedelta(days=183)
        price_6m, p6d = nearest_price(monthly, six_month_date)
        row["price_at_snapshot"] = price_at
        row["price_at_snapshot_date"] = price_date.strftime("%Y-%m-%d") if price_date else ""
        row["price_+6m"] = price_6m
        row["price_+6m_date"] = p6d.strftime("%Y-%m-%d") if p6d else ""
        if price_at and price_6m and not math.isnan(price_at) and not math.isnan(price_6m) and price_at != 0:
            row["forward_6m_return"] = price_6m / price_at - 1.0
        else:
            row["forward_6m_return"] = math.nan
        snapshots.append(row)
    return snapshots


def write_rows(path, rows, header=None):
    mode = "w"
    if os.path.exists(path):
        mode = "a"
    with open(path, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header or (rows[0].keys() if rows else []))
        if mode == "w":
            writer.writeheader()
        for r in rows:
            writer.writerow(r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default="ml/tickers.txt")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="ml/data/historical_snapshots_validation.csv")
    parser.add_argument("--quarters", type=int, default=20)
    args = parser.parse_args()

    if not API_KEY:
        print("Missing ALPHAVANTAGE_API_KEY in environment", file=sys.stderr)
        sys.exit(1)

    tickers = load_tickers(args.tickers, limit=args.limit)
    rl = RateLimiter(calls_per_minute=300)
    session = requests.Session()
    for i, t in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Collecting {t}")
        data = collect_for_ticker(session, rl, t, None)
        snaps = build_snapshots(t, data, max_quarters=args.quarters)
        if snaps:
            write_rows(args.output, snaps, header=list(snaps[0].keys()))
        else:
            print(f"  no monthly data for {t}")
    print("Done. Output:", args.output)


if __name__ == "__main__":
    main()
