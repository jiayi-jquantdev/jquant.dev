#!/usr/bin/env python3
"""Produce data quality report and retrain adding clean backward-looking momentum features.
Saves model to `ml/models/snapshot_xgb_v3_mom.pkl` and metrics to `ml/models/metrics_v3_mom.json`.
"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_absolute_error


def data_quality_report(df, drop_patterns=None):
    if drop_patterns is None:
        drop_patterns = ['latest_close','52Week','50Day','200Day','price_vs','ForwardPE','Analyst','AnalystTargetPrice']
    cols = df.columns.tolist()
    to_drop = [c for c in cols if any(p in c for p in drop_patterns)]
    df2 = df.drop(columns=to_drop, errors='ignore')
    total = len(df2)
    non_missing_target = df2['forward_6m_return'].notna().sum()
    pct_non_missing_target = 100.0 * non_missing_target / total if total else 0
    missing_by_col = (df2.isna().mean() * 100).sort_values()
    desc = df2['forward_6m_return'].describe()
    # histogram bins
    hist = np.histogram(df2['forward_6m_return'].dropna(), bins=20)
    years = pd.to_datetime(df2['snapshot_date'], errors='coerce').dt.year.value_counts().sort_index()
    return {
        'rows_total': int(total),
        'non_missing_target': int(non_missing_target),
        'pct_non_missing_target': float(pct_non_missing_target),
        'missing_by_col_pct': missing_by_col.to_dict(),
        'target_describe': desc.to_dict(),
        'target_hist_bins': hist[1].tolist(),
        'target_hist_counts': hist[0].tolist(),
        'rows_by_year': years.to_dict(),
        'dropped_columns': to_drop,
    }


def run(input_csv='ml/data/historical_snapshots_1000_v3.csv'):
    df = pd.read_csv(input_csv)
    df = df.replace([np.inf, -np.inf], np.nan)
    report = data_quality_report(df)
    print('Data quality:')
    print(' Total rows:', report['rows_total'])
    print(' Non-missing target rows:', report['non_missing_target'], f"({report['pct_non_missing_target']:.2f}%)")
    print(' Dropped columns (price/forward patterns):', report['dropped_columns'])
    print('\nTop 10 least-missing columns:')
    for k,v in list(report['missing_by_col_pct'].items())[:10]:
        pass
    # show top and bottom missing
    items = list(report['missing_by_col_pct'].items())
    print('\nSample missing% (first 10):')
    for k,v in items[:10]:
        print(f'  {k}: {v:.2f}%')
    print('\nTarget describe:')
    for k,v in report['target_describe'].items():
        print(f'  {k}: {v}')

    # Ensure clean momentum features exist; if not, warn
    momentum_cols = ['r1m','r3m','r6m','r12m']
    present_mom = [c for c in momentum_cols if c in df.columns]
    print('\nMomentum columns present:', present_mom)
    missing_mom = [c for c in momentum_cols if c not in df.columns]
    if missing_mom:
        print(' Missing momentum columns:', missing_mom)

    # Build feature list: fundamental ratios + momentum
    fundamentals = [
        'totalRevenue','netIncome','totalAssets','totalLiabilities','operatingCashflow',
        'eps_ttm','pe','pb','pe_sector_median','pb_sector_median','pe_vs_sector','pb_vs_sector',
        'pe_mean_by_stock','pe_vs_hist_mean'
    ]
    features = [f for f in fundamentals if f in df.columns] + present_mom
    print('\nUsing features:', features)

    # prepare dataset
    df = df.dropna(subset=['forward_6m_return','snapshot_date'])
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].dropna().unique())
    if len(years) < 2:
        raise SystemExit('Not enough years for walk-forward CV')

    import xgboost as xgb
    r2s = []
    maes = []
    models = []
    for i in range(len(years)-1):
        train_years = [y for y in years if y <= years[i]]
        test_year = years[i+1]
        train = df[df['year'].isin(train_years)]
        test = df[df['year'] == test_year]
        if len(train) < 50 or len(test) < 30:
            print(f' Skipping fold train<={train_years[-1]} test={test_year} due to small size (train={len(train)} test={len(test)})')
            continue
        X_train = train[features].fillna(0)
        y_train = train['forward_6m_return']
        X_test = test[features].fillna(0)
        y_test = test['forward_6m_return']
        model = xgb.XGBRegressor(n_estimators=300, max_depth=5, random_state=42, verbosity=0)
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        r2 = r2_score(y_test, pred)
        mae = mean_absolute_error(y_test, pred)
        print(f' Fold train<={train_years[-1]} test={test_year} -> R2={r2:.4f} MAE={mae:.4f} (train={len(train)} test={len(test)})')
        r2s.append(r2); maes.append(mae); models.append((model, X_test.columns))

    if not r2s:
        print('No valid folds to evaluate (size thresholds). Aborting.')
        return

    print('Mean fold R2:', float(np.mean(r2s)), 'Mean MAE:', float(np.mean(maes)))

    # final model on all but last year
    final_train = df[df['year'] < years[-1]]
    final_test = df[df['year'] == years[-1]]
    X_tr = final_train[features].fillna(0); y_tr = final_train['forward_6m_return']
    X_te = final_test[features].fillna(0); y_te = final_test['forward_6m_return']
    final_model = xgb.XGBRegressor(n_estimators=500, max_depth=6, random_state=42, verbosity=0)
    final_model.fit(X_tr, y_tr)
    pred_te = final_model.predict(X_te)
    r2_final = r2_score(y_te, pred_te) if len(y_te)>1 and y_te.nunique()>1 else 0.0
    mae_final = mean_absolute_error(y_te, pred_te)
    print('Final R2:', r2_final, 'Final MAE:', mae_final, f'(test rows={len(final_test)})')

    # feature importances
    importances = dict(zip(features, final_model.feature_importances_.tolist()))
    top_feats = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:20]
    print('\nTop features:')
    for f,v in top_feats:
        print(f'  {f}: {v:.4f}')

    os.makedirs('ml/models', exist_ok=True)
    joblib = __import__('joblib')
    joblib.dump(final_model, 'ml/models/snapshot_xgb_v3_mom.pkl')
    metrics = {'fold_r2s': r2s, 'fold_maes': maes, 'mean_fold_r2': float(np.mean(r2s)), 'mean_fold_mae': float(np.mean(maes)), 'final_r2': float(r2_final), 'final_mae': float(mae_final), 'features': features, 'top_features': top_feats}
    with open('ml/models/metrics_v3_mom.json','w') as f:
        json.dump(metrics, f, indent=2)
    print('\nSaved model to ml/models/snapshot_xgb_v3_mom.pkl and metrics to ml/models/metrics_v3_mom.json')


if __name__ == '__main__':
    run()
