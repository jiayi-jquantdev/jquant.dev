#!/usr/bin/env python3
"""Automated training on expanded features.

Produces rolling CV folds, final test metrics, and permutation importances.
Saves model to `ml/models/snapshot_xgb_auto_expanded.pkl` and metrics to
`ml/models/metrics_auto_expanded.json`.
"""
import os
import json
import math
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.inspection import permutation_importance


def load_data(path):
    df = pd.read_csv(path)
    return df


def select_features(df):
    # conservative exclusion to avoid leakage: drop any timestamp, identifier,
    # forward-looking, price-derived, or target columns
    exclude_exact = set([
        'ticker', 'snapshot_date', 'collection_date', 'price_at_snapshot', 'price_at_snapshot_date',
        'price_+6m', 'price_+6m_date', 'forward_6m_return', 'forward_6m_return_winsor', 'target_winsor'
    ])
    exclude_substrings = ['forward', 'future', 'price', 'close', 'latest', 'analyst', 'estimate', 'target', 'ma_', '52week', '50day', '200day']
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    features = []
    for c in numcols:
        if c in exclude_exact:
            continue
        lower = c.lower()
        if any(s in lower for s in exclude_substrings):
            continue
        features.append(c)
    return features


def winsorize_target(df, col='forward_6m_return', low_pct=0.01, high_pct=0.99):
    vals = df[col].dropna()
    low = vals.quantile(low_pct)
    high = vals.quantile(high_pct)
    out = df.copy()
    out['target_winsor'] = out[col].clip(lower=low, upper=high)
    return out, float(low), float(high)


def fix_leakage_by_lagging(df):
    """Create lagged (previous-snapshot) versions of suspicious forward-looking columns.

    For any numeric column whose name suggests forward-looking/price/analyst/estimate
    content, create `lag_<col>` as the previous available value for the same ticker
    (groupby shift). Also create a trailing PE feature where possible.
    This converts potential forward info into a conservative backward-looking proxy.
    """
    df = df.copy()
    suspect_substr = ['forward', 'future', 'analyst', 'estimate', 'target', 'price_+','price_plus', 'latest', 'price_vs', 'ma_', '52week', '50day', '200day', 'forwardpe']
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    # ensure snapshot_date exists and is datetime
    if 'snapshot_date' in df.columns:
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    else:
        return df
    for c in numcols:
        lower = c.lower()
        if any(s in lower for s in suspect_substr):
            # create lagged version name that avoids suspect substrings
            lagname = f'lag_{c}'
            df = df.sort_values(['ticker','snapshot_date'])
            try:
                df[lagname] = df.groupby('ticker')[c].shift(1)
            except Exception:
                df[lagname] = np.nan
    # create trailing PE if possible
    if 'price_at_snapshot' in df.columns and 'eps_ttm' in df.columns:
        with np.errstate(divide='ignore', invalid='ignore'):
            df['pe_trailing'] = df['price_at_snapshot'] / df['eps_ttm']
    return df


def sanitize_and_scale(df, features):
    X = df[features].replace([np.inf, -np.inf], np.nan).fillna(0).copy()
    # per-feature winsorize
    for f in features:
        col = X[f]
        if col.dropna().empty:
            continue
        lo = col.quantile(0.01)
        hi = col.quantile(0.99)
        X[f] = col.clip(lower=lo, upper=hi)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    return Xs, scaler


def rolling_walk_forward(df, features, target_col='target_winsor', train_years=3, min_train=200, min_test=100):
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date', target_col])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].dropna().unique())
    folds = []
    import xgboost as xgb
    for start in range(0, len(years) - train_years):
        train_years_range = years[start:start+train_years]
        test_year = years[start+train_years]
        train_idx = df['year'].isin(train_years_range)
        test_idx = df['year'] == test_year
        train = df[train_idx]
        test = df[test_idx]
        if len(train) < min_train or len(test) < min_test:
            continue
        X_train, _ = sanitize_and_scale(train, features)
        X_test, _ = sanitize_and_scale(test, features)
        y_train = train[target_col].values
        y_test = test[target_col].values
        model = xgb.XGBRegressor(n_estimators=400, max_depth=6, learning_rate=0.05, random_state=42, verbosity=0)
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        r2 = float(r2_score(y_test, pred))
        mae = float(mean_absolute_error(y_test, pred))
        folds.append({'train_years':[int(y) for y in train_years_range], 'test_year':int(test_year), 'r2':r2, 'mae':mae, 'train_n':int(len(train)), 'test_n':int(len(test)), 'model': model, 'X_test': X_test, 'y_test': y_test})
        print(f"Fold train={train_years_range} test={test_year} -> R2={r2:.4f} MAE={mae:.4f} (n_train={len(train)} n_test={len(test)})")
    return folds


def final_train_and_importance(df, features, target_col='target_winsor'):
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date', target_col])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].dropna().unique())
    if len(years) < 2:
        raise SystemExit('Not enough years')
    train = df[df['year'] < years[-1]]
    test = df[df['year'] == years[-1]]
    X_tr, scaler = sanitize_and_scale(train, features)
    X_te = scaler.transform(df.loc[test.index, features].replace([np.inf, -np.inf], np.nan).fillna(0)) if len(test)>0 else np.array([])
    y_tr = train[target_col].values
    y_te = test[target_col].values
    import xgboost as xgb
    final_model = xgb.XGBRegressor(n_estimators=800, max_depth=6, learning_rate=0.05, random_state=42, verbosity=0)
    final_model.fit(X_tr, y_tr)
    pred = final_model.predict(X_te) if len(test)>0 else np.array([])
    r2_final = float(r2_score(y_te, pred)) if len(y_te)>1 and np.unique(y_te).shape[0]>1 else 0.0
    mae_final = float(mean_absolute_error(y_te, pred)) if len(y_te)>0 else float('nan')

    # permutation importance
    perm = permutation_importance(final_model, X_te, y_te, n_repeats=10, random_state=42, n_jobs=-1) if len(y_te)>0 else None
    importances = []
    if perm is not None:
        for i,feat in enumerate(features):
            importances.append((feat, float(perm.importances_mean[i])))
        importances = sorted(importances, key=lambda x: x[1], reverse=True)
    return final_model, scaler, r2_final, mae_final, importances


def save_artifacts(model, scaler, metrics, model_path='ml/models/snapshot_xgb_auto_expanded.pkl', metrics_path='ml/models/metrics_auto_expanded.json'):
    os.makedirs('ml/models', exist_ok=True)
    import joblib
    joblib.dump({'model': model, 'scaler': scaler}, model_path)
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)


def main():
    input_csv = os.getenv('TRAIN_INPUT','ml/data/historical_snapshots_1000_v3_expanded.csv')
    df = load_data(input_csv)
    # winsorize target first
    df, low, high = winsorize_target(df, 'forward_6m_return')
    # fix leakage by converting suspect forward-looking columns into lagged features
    df = fix_leakage_by_lagging(df)
    features = select_features(df)
    print('Feature count:', len(features))
    folds = rolling_walk_forward(df, features, target_col='target_winsor', train_years=3, min_train=200, min_test=100)
    serial_folds = []
    for f in folds:
        serial_folds.append({'train_years':f['train_years'],'test_year':f['test_year'],'r2':f['r2'],'mae':f['mae'],'train_n':f['train_n'],'test_n':f['test_n']})
    mean_fold_r2 = float(np.mean([f['r2'] for f in folds])) if folds else None
    mean_fold_mae = float(np.mean([f['mae'] for f in folds])) if folds else None

    final_model, scaler, final_r2, final_mae, importances = final_train_and_importance(df, features, target_col='target_winsor')
    top30 = importances[:30]

    metrics = {'winsor_low': low, 'winsor_high': high, 'folds': serial_folds, 'mean_fold_r2': mean_fold_r2, 'mean_fold_mae': mean_fold_mae, 'final_r2': final_r2, 'final_mae': final_mae, 'feature_count': len(features), 'top30_permutation_importances': top30}
    save_artifacts(final_model, scaler, metrics)
    print('\nDone. Summary:')
    print(' mean_fold_r2:', mean_fold_r2)
    print(' final_r2:', final_r2, 'final_mae:', final_mae)
    print(' feature_count:', len(features))
    print('\nTop 30 permutation importances:')
    for f,v in top30:
        print(f, v)


if __name__ == '__main__':
    main()
