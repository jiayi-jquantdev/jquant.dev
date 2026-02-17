#!/usr/bin/env python3
"""Load featurized v3 CSV, drop price-derived and forward-looking features,
and retrain using only backward-looking fundamentals + momentum.
Saves model to `ml/models/snapshot_xgb_v3_clean.pkl` and writes metrics to `ml/models/metrics_v3_clean.json`.
"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_absolute_error

def main(input_csv='ml/data/historical_snapshots_1000_v3.csv'):
    df = pd.read_csv(input_csv)
    df = df.replace([np.inf, -np.inf], np.nan)
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')

    # Drop price-derived and forward-looking columns
    drop_patterns = ['latest_close','52Week','50Day','200Day','price_vs','ForwardPE','Analyst','AnalystTargetPrice']
    cols = list(df.columns)
    to_drop = [c for c in cols if any(p in c for p in drop_patterns)]
    if to_drop:
        print('Dropping', len(to_drop), 'columns')
        df = df.drop(columns=to_drop, errors='ignore')

    # Candidate backward-looking features
    candidate_features = [
        'QuarterlyRevenueGrowthYOY','QuarterlyEarningsGrowthYOY','RevenueTTM','GrossProfitTTM',
        'EBITDA','EPS','ReturnOnEquityTTM','ReturnOnAssetsTTM','ProfitMargin','netIncome','totalRevenue',
        'totalAssets','totalLiabilities','operatingCashflow','gross_margin','operating_margin','ebitda_margin',
        'current_ratio','quick_ratio','debt_to_equity',
        'pe','pb','pe_vs_sector','pb_vs_sector','pe_vs_hist_mean',
        'r1m','r3m','r6m','r12m','r6m_vs_sector'
    ]
    features = [f for f in candidate_features if f in df.columns]
    print('Using features:', features)

    # clean target and rows
    df = df.dropna(subset=['forward_6m_return','snapshot_date'])
    df = df[df['snapshot_date'].dt.year.notna()]
    df['year'] = df['snapshot_date'].dt.year

    years = sorted(df['year'].unique())
    if len(years) < 2:
        raise SystemExit('Not enough years for walk-forward CV')

    import xgboost as xgb
    r2s = []
    maes = []
    for i in range(len(years)-1):
        train_years = [y for y in years if y <= years[i]]
        test_year = years[i+1]
        train = df[df['year'].isin(train_years)]
        test = df[df['year']==test_year]
        if train.empty or test.empty:
            continue
        X_train = train[features].fillna(0)
        y_train = train['forward_6m_return']
        X_test = test[features].fillna(0)
        y_test = test['forward_6m_return']
        model = xgb.XGBRegressor(n_estimators=200, max_depth=5, random_state=42, verbosity=0)
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        r2 = r2_score(y_test, pred)
        mae = mean_absolute_error(y_test, pred)
        print(f'Fold train<={train_years[-1]} test={test_year} -> R2={r2:.4f} MAE={mae:.4f}')
        r2s.append(r2); maes.append(mae)

    print('Mean R2:', float(np.mean(r2s)) if r2s else None)

    # final train/test (last year)
    final_train = df[df['year'] < years[-1]]
    final_test = df[df['year'] == years[-1]]
    X_tr = final_train[features].fillna(0); y_tr = final_train['forward_6m_return']
    X_te = final_test[features].fillna(0); y_te = final_test['forward_6m_return']
    final_model = xgb.XGBRegressor(n_estimators=500, max_depth=6, random_state=42, verbosity=0)
    final_model.fit(X_tr, y_tr)
    pred_te = final_model.predict(X_te)
    r2_final = r2_score(y_te, pred_te)
    mae_final = mean_absolute_error(y_te, pred_te)
    print('Final R2:', r2_final, 'MAE:', mae_final)

    os.makedirs('ml/models', exist_ok=True)
    joblib = __import__('joblib')
    joblib.dump(final_model, 'ml/models/snapshot_xgb_v3_clean.pkl')
    metrics = {'r2': float(r2_final), 'mae': float(mae_final), 'features_used': features}
    with open('ml/models/metrics_v3_clean.json','w') as f:
        json.dump(metrics, f, indent=2)
    print('Saved model and metrics')


if __name__ == '__main__':
    main()
