#!/usr/bin/env python3
"""Comprehensive training pipeline:
- Winsorize target (1st-99th percentile)
- Add fundamental ratios (margins, liquidity, leverage, ROA/ROE, FCF yield)
- Compute Piotroski-like score from available fields
- Add sector-relative momentum
- Perform rolling walk-forward CV (multiple rolling folds)
- Train final XGBoost and save metrics/model
"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_absolute_error


def winsorize_target(df, col='forward_6m_return', low_pct=0.01, high_pct=0.99):
    vals = df[col].dropna()
    low = vals.quantile(low_pct)
    high = vals.quantile(high_pct)
    df[col+'_winsor'] = df[col].clip(lower=low, upper=high)
    return df, float(low), float(high)


def compute_fundamentals(df):
    # margins
    df['net_margin'] = df['netIncome'] / df['totalRevenue']
    if 'grossProfit' in df.columns:
        df['gross_margin'] = df['grossProfit'] / df['totalRevenue']
    else:
        df['gross_margin'] = np.nan
    if 'operatingIncome' in df.columns:
        df['operating_margin'] = df['operatingIncome'] / df['totalRevenue']
    else:
        df['operating_margin'] = np.nan

    # liquidity
    if 'currentAssets' in df.columns and 'currentLiabilities' in df.columns:
        df['current_ratio'] = df['currentAssets'] / df['currentLiabilities']
    else:
        df['current_ratio'] = np.nan
    if 'inventories' in df.columns:
        df['quick_ratio'] = (df['currentAssets'] - df['inventories']) / df['currentLiabilities']
    else:
        df['quick_ratio'] = np.nan

    # leverage
    if 'totalShareholderEquity' in df.columns:
        df['debt_to_equity'] = df['totalLiabilities'] / (df['totalShareholderEquity'].replace({0:np.nan}))
    else:
        # proxy equity = assets - liabilities
        df['debt_to_equity'] = df['totalLiabilities'] / (df['totalAssets'] - df['totalLiabilities']).replace({0:np.nan})

    # interest coverage
    if 'ebit' in df.columns and 'interestExpense' in df.columns:
        df['interest_coverage'] = df['ebit'] / df['interestExpense'].replace({0:np.nan})
    else:
        df['interest_coverage'] = np.nan

    # ROA, ROE
    df['roa'] = df['netIncome'] / df['totalAssets']
    df['roe'] = df['netIncome'] / (df['totalAssets'] - df['totalLiabilities']).replace({0:np.nan})

    # free cash flow yield (approx)
    if 'operatingCashflow' in df.columns:
        if 'capitalExpenditures' in df.columns:
            df['free_cash_flow'] = df['operatingCashflow'] - df['capitalExpenditures']
        else:
            df['free_cash_flow'] = df['operatingCashflow']
        df['fcf_yield_rev'] = df['free_cash_flow'] / df['totalRevenue'].replace({0:np.nan})
    else:
        df['free_cash_flow'] = np.nan
        df['fcf_yield_rev'] = np.nan

    return df


def compute_piotroski(df):
    # approximate Piotroski-like score using available columns and prior snapshot where possible
    df = df.sort_values(['ticker','snapshot_date'])
    df['piotroski'] = 0
    # compute shifted values per ticker
    grp = df.groupby('ticker')
    prev = grp.shift(1)

    # 1. Positive net income
    df['p1'] = (df['netIncome'] > 0).astype(int)
    # 2. Positive operating cash flow
    df['p2'] = (df['operatingCashflow'] > 0).astype(int)
    # 3. Accruals: CFO > Net Income
    df['p3'] = (df['operatingCashflow'] > df['netIncome']).astype(int)
    # 4. Leverage decreased (totalLiabilities/totalAssets decreased)
    lev = (df['totalLiabilities'] / df['totalAssets']).replace([np.inf,-np.inf],np.nan)
    prev_lev = (prev['totalLiabilities'] / prev['totalAssets']).replace([np.inf,-np.inf],np.nan)
    df['p4'] = (lev < prev_lev).astype(int)
    # 5. Current ratio improved (use raw currentAssets/currentLiabilities from prev)
    if 'currentAssets' in df.columns and 'currentLiabilities' in df.columns:
        cur = (df['currentAssets'] / df['currentLiabilities']).replace([np.inf,-np.inf],np.nan)
        prev_cur = (prev['currentAssets'] / prev['currentLiabilities']).replace([np.inf,-np.inf],np.nan)
        df['p5'] = (cur > prev_cur).astype(int)
    else:
        df['p5'] = 0
    # 6. No new shares (proxy: p6 not computed)
    df['p6'] = 0
    # 7. Gross margin improved
    if 'grossProfit' in df.columns and 'totalRevenue' in df.columns:
        gm = (df['grossProfit'] / df['totalRevenue']).replace([np.inf,-np.inf],np.nan)
        prev_gm = (prev['grossProfit'] / prev['totalRevenue']).replace([np.inf,-np.inf],np.nan)
        df['p7'] = (gm > prev_gm).astype(int)
    else:
        df['p7'] = 0
    # 8. Asset turnover increased (revenue/totalAssets)
    turnover = (df['totalRevenue'] / df['totalAssets']).replace([np.inf,-np.inf],np.nan)
    prev_turn = (prev['totalRevenue'] / prev['totalAssets']).replace([np.inf,-np.inf],np.nan)
    df['p8'] = (turnover > prev_turn).astype(int)
    # 9. Operating margin improved
    if 'operatingIncome' in df.columns and 'totalRevenue' in df.columns:
        om = (df['operatingIncome'] / df['totalRevenue']).replace([np.inf,-np.inf],np.nan)
        prev_om = (prev['operatingIncome'] / prev['totalRevenue']).replace([np.inf,-np.inf],np.nan)
        df['p9'] = (om > prev_om).astype(int)
    else:
        df['p9'] = 0

    # sum available points
    pts = ['p1','p2','p3','p4','p5','p6','p7','p8','p9']
    df['piotroski'] = df[pts].fillna(0).sum(axis=1)
    # clean up helpers
    df = df.drop(columns=['p1','p2','p3','p4','p5','p6','p7','p8','p9','lev','turnover'], errors='ignore')
    return df


def compute_sector_relative(df):
    # compute median r6m and r12m per (snapshot_date, sector)
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    grp = df.groupby(['snapshot_date','sector'])
    med_r6 = grp['r6m'].transform('median')
    med_r12 = grp['r12m'].transform('median')
    df['r6m_vs_sector'] = df['r6m'] - med_r6
    df['r12m_vs_sector'] = df['r12m'] - med_r12
    # relative strength score: r6m / (sector median + tiny)
    df['rel_strength'] = df['r6m'] / (med_r6 + 1e-9)
    return df


def rolling_walk_forward(df, features, target_col='forward_6m_return_winsor', train_years=3, min_train=200, min_test=100):
    df['year'] = pd.to_datetime(df['snapshot_date']).dt.year
    years = sorted(df['year'].dropna().unique())
    folds = []
    import xgboost as xgb
    for start in range(0, len(years) - train_years):
        train_years_range = years[start:start+train_years]
        test_year = years[start+train_years]
        train = df[df['year'].isin(train_years_range)]
        test = df[df['year'] == test_year]
        if len(train) < min_train or len(test) < min_test:
            continue
        X_train = train[features].fillna(0)
        y_train = train[target_col]
        X_test = test[features].fillna(0)
        y_test = test[target_col]
        model = xgb.XGBRegressor(n_estimators=400, max_depth=6, learning_rate=0.05, random_state=42, verbosity=0)
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        r2 = r2_score(y_test, pred)
        mae = mean_absolute_error(y_test, pred)
        folds.append({'train_years':train_years_range, 'test_year':test_year, 'r2':float(r2), 'mae':float(mae), 'train_n':len(train), 'test_n':len(test), 'model':model})
        print(f"Fold train={train_years_range} test={test_year} -> R2={r2:.4f} MAE={mae:.4f} (n_train={len(train)} n_test={len(test)})")
    return folds


def sanitize_features(df, features, low_pct=0.01, high_pct=0.99):
    # replace infs, then winsorize each feature to remove extreme values that break XGBoost
    df[features] = df[features].replace([np.inf, -np.inf], np.nan)
    for f in features:
        col = df[f]
        if col.dropna().empty:
            continue
        lo = col.quantile(low_pct)
        hi = col.quantile(high_pct)
        df[f] = col.clip(lower=lo, upper=hi)
    return df

def main(input_csv='ml/data/historical_snapshots_1000_v3.csv'):
    df = pd.read_csv(input_csv)
    df = df.replace([np.inf, -np.inf], np.nan)
    # drop obvious forward/price fields
    drop_patterns = ['latest_close','52Week','50Day','200Day','price_vs','ForwardPE','Analyst','AnalystTargetPrice']
    to_drop = [c for c in df.columns if any(p in c for p in drop_patterns)]
    df = df.drop(columns=to_drop, errors='ignore')

    # winsorize target
    df, low, high = winsorize_target(df, col='forward_6m_return')
    print('Winsorized target at', low, high)

    # compute fundamentals
    df = compute_fundamentals(df)
    df = compute_piotroski(df)
    df = compute_sector_relative(df)

    # build feature list
    core = [
        'totalRevenue','netIncome','totalAssets','totalLiabilities','operatingCashflow',
        'eps_ttm','pe','pb','pe_sector_median','pb_sector_median','pe_vs_sector','pb_vs_sector','pe_mean_by_stock','pe_vs_hist_mean',
        'net_margin','gross_margin','operating_margin','current_ratio','quick_ratio','debt_to_equity','interest_coverage','roa','roe','fcf_yield_rev','piotroski'
    ]
    momentum = ['r1m','r3m','r6m','r12m','r6m_vs_sector','r12m_vs_sector','rel_strength']
    features = [f for f in core+momentum if f in df.columns]
    print('Features count:', len(features))

    # filter rows with target and date
    df = df.dropna(subset=['forward_6m_return_winsor','snapshot_date'])
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')

    # sanitize features before training
    df = sanitize_features(df, features)

    # rolling walk-forward
    folds = rolling_walk_forward(df, features, target_col='forward_6m_return_winsor', train_years=3, min_train=200, min_test=100)
    if not folds:
        raise SystemExit('No valid folds; check date distribution or thresholds')
    r2s = [f['r2'] for f in folds]
    maes = [f['mae'] for f in folds]
    mean_r2 = float(np.mean(r2s))
    mean_mae = float(np.mean(maes))
    print('Mean fold R2:', mean_r2, 'Mean MAE:', mean_mae)

    # final train on all but last year
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].dropna().unique())
    final_train = df[df['year'] < years[-1]]
    final_test = df[df['year'] == years[-1]]
    X_tr = final_train[features].fillna(0); y_tr = final_train['forward_6m_return_winsor']
    X_te = final_test[features].fillna(0); y_te = final_test['forward_6m_return_winsor']
    import xgboost as xgb
    final_model = xgb.XGBRegressor(n_estimators=800, max_depth=6, learning_rate=0.05, random_state=42, verbosity=0)
    final_model.fit(X_tr, y_tr)
    pred = final_model.predict(X_te)
    r2_final = float(r2_score(y_te, pred)) if len(y_te)>1 and y_te.nunique()>1 else 0.0
    mae_final = float(mean_absolute_error(y_te, pred))
    print('Final test R2:', r2_final, 'MAE:', mae_final, f'(test_n={len(final_test)})')

    # feature importances
    importances = dict(zip(features, final_model.feature_importances_.tolist()))
    top20 = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:20]
    print('\nTop 20 features:')
    for f,v in top20:
        print(f'  {f}: {v:.4f}')

    # save artifacts
    os.makedirs('ml/models', exist_ok=True)
    joblib = __import__('joblib')
    joblib.dump(final_model, 'ml/models/snapshot_xgb_v3_improved.pkl')
    serial_folds = []
    for f in folds:
        serial_folds.append({'train_years':[int(y) for y in f['train_years']], 'test_year':int(f['test_year']), 'r2':f['r2'], 'mae':f['mae'], 'train_n':int(f['train_n']), 'test_n':int(f['test_n'])})
    metrics = {'winsor_low': low, 'winsor_high': high, 'folds': serial_folds, 'mean_fold_r2': mean_r2, 'mean_fold_mae': mean_mae, 'final_r2': r2_final, 'final_mae': mae_final, 'top20': top20}
    with open('ml/models/metrics_v3_improved.json','w') as f:
        json.dump(metrics, f, indent=2)
    print('Saved model and metrics to ml/models')


if __name__ == '__main__':
    import os
    input_csv = os.getenv('TRAIN_INPUT', 'ml/data/historical_snapshots_1000_v3.csv')
    main(input_csv)
