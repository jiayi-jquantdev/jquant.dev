#!/usr/bin/env python3
"""Feature selection + hyperparameter tuning trainer.

1. Winsorize target and fix leakage (lagging).
2. Run rolling walk-forward folds, collect permutation importances per-fold.
3. Aggregate importances and select top-K features.
4. Run a randomized search over XGBoost on training years and evaluate on final year.
5. Save model and metrics to `ml/models/`.
"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.inspection import permutation_importance
from sklearn.model_selection import RandomizedSearchCV


def load_data(path):
    return pd.read_csv(path)


def winsorize_target(df, col='forward_6m_return', low_pct=0.01, high_pct=0.99):
    vals = df[col].dropna()
    low = vals.quantile(low_pct)
    high = vals.quantile(high_pct)
    out = df.copy()
    out['target_winsor'] = out[col].clip(lower=low, upper=high)
    return out, float(low), float(high)


def fix_leakage_by_lagging(df):
    df = df.copy()
    suspect_substr = ['forward', 'future', 'analyst', 'estimate', 'target', 'price_+','price_plus', 'latest', 'price_vs', 'ma_', '52week', '50day', '200day', 'forwardpe']
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    if 'snapshot_date' in df.columns:
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    else:
        return df
    for c in numcols:
        lower = c.lower()
        if any(s in lower for s in suspect_substr):
            lagname = f'lag_{c}'
            df = df.sort_values(['ticker','snapshot_date'])
            try:
                df[lagname] = df.groupby('ticker')[c].shift(1)
            except Exception:
                df[lagname] = np.nan
    if 'price_at_snapshot' in df.columns and 'eps_ttm' in df.columns:
        with np.errstate(divide='ignore', invalid='ignore'):
            df['pe_trailing'] = df['price_at_snapshot'] / df['eps_ttm']
    return df


def select_numeric_features(df):
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    # remove explicit target and identifiers and original forward/price/analyst columns
    blacklist = set(['forward_6m_return','target_winsor'])
    suspect_substr = ['forward', 'future', 'analyst', 'estimate', 'target', 'price_+', 'price_at_snapshot', 'price_plus', 'latest', 'price_vs', 'ma_', '52week', '50day', '200day', 'forwardpe']
    features = []
    for c in numcols:
        if c in blacklist:
            continue
        lower = c.lower()
        # keep lagged features and pe_trailing explicitly
        if lower.startswith('lag_') or lower == 'pe_trailing':
            features.append(c)
            continue
        # exclude any suspect originals
        if any(s in lower for s in suspect_substr):
            continue
        features.append(c)
    return features


def sanitize_and_scale(df, features, scaler=None):
    X = df[features].replace([np.inf, -np.inf], np.nan).fillna(0).copy()
    for f in features:
        col = X[f]
        if col.dropna().empty:
            continue
        lo = col.quantile(0.01)
        hi = col.quantile(0.99)
        X[f] = col.clip(lower=lo, upper=hi)
    if scaler is None:
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)
    else:
        Xs = scaler.transform(X)
    return Xs, scaler


def rolling_folds(df, train_years=3, min_train=200, min_test=100):
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].dropna().unique())
    folds = []
    for start in range(0, len(years)-train_years):
        train_years_range = years[start:start+train_years]
        test_year = years[start+train_years]
        train_idx = df['year'].isin(train_years_range)
        test_idx = df['year'] == test_year
        train = df[train_idx]
        test = df[test_idx]
        if len(train) < min_train or len(test) < min_test:
            continue
        folds.append({'train_idx':train.index, 'test_idx':test.index, 'train_years':train_years_range, 'test_year':test_year})
    return folds


def aggregate_permutation_importances(df, features, folds):
    import xgboost as xgb
    agg = {f:[] for f in features}
    for fold in folds:
        train = df.loc[fold['train_idx']]
        test = df.loc[fold['test_idx']]
        X_tr, scaler = sanitize_and_scale(train, features)
        X_te, _ = sanitize_and_scale(test, features, scaler)
        y_tr = train['target_winsor'].values
        y_te = test['target_winsor'].values
        model = xgb.XGBRegressor(n_estimators=400, max_depth=6, learning_rate=0.05, random_state=42, verbosity=0)
        model.fit(X_tr, y_tr)
        try:
            perm = permutation_importance(model, X_te, y_te, n_repeats=8, random_state=42, n_jobs=4)
        except Exception:
            continue
        for i,f in enumerate(features):
            agg[f].append(float(perm.importances_mean[i]))
    # aggregate by mean
    agg_mean = {f: float(np.mean(vals)) if len(vals)>0 else 0.0 for f,vals in agg.items()}
    # sort
    sorted_feats = sorted(agg_mean.items(), key=lambda x: x[1], reverse=True)
    return sorted_feats


def final_tune_and_eval(df, top_features, random_search_iters=30):
    import xgboost as xgb
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].dropna().unique())
    if len(years) < 2:
        raise SystemExit('Not enough years for final eval')
    train = df[df['year'] < years[-1]]
    test = df[df['year'] == years[-1]]
    X_tr, scaler = sanitize_and_scale(train, top_features)
    X_te, _ = sanitize_and_scale(test, top_features, scaler)
    y_tr = train['target_winsor'].values
    y_te = test['target_winsor'].values
    base = xgb.XGBRegressor(random_state=42, verbosity=0)
    param_dist = {
        'n_estimators': [200,400,800],
        'max_depth': [3,6,9],
        'learning_rate': [0.01,0.03,0.05,0.1],
        'subsample': [0.6,0.8,1.0],
        'colsample_bytree': [0.5,0.8,1.0]
    }
    rs = RandomizedSearchCV(base, param_distributions=param_dist, n_iter=min(random_search_iters,40), cv=3, scoring='r2', n_jobs=4, random_state=42, verbose=1)
    rs.fit(X_tr, y_tr)
    best = rs.best_estimator_
    pred = best.predict(X_te)
    r2f = float(r2_score(y_te, pred)) if len(y_te)>1 and np.unique(y_te).shape[0]>1 else 0.0
    maef = float(mean_absolute_error(y_te, pred)) if len(y_te)>0 else float('nan')
    return best, scaler, r2f, maef, rs.best_params_


def save_model_and_metrics(model, scaler, metrics, model_path='ml/models/snapshot_xgb_fs_tuned.pkl', metrics_path='ml/models/metrics_fs_tuned.json'):
    os.makedirs('ml/models', exist_ok=True)
    import joblib
    joblib.dump({'model': model, 'scaler': scaler}, model_path)
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)


def main():
    input_csv = os.getenv('TRAIN_INPUT','ml/data/historical_snapshots_1000_v3_expanded.csv')
    df = load_data(input_csv)
    df, low, high = winsorize_target(df, 'forward_6m_return')
    df = fix_leakage_by_lagging(df)
    features = select_numeric_features(df)
    print('Numeric feature count:', len(features))
    folds = rolling_folds(df, train_years=3, min_train=200, min_test=100)
    print('Fold count:', len(folds))
    sorted_feats = aggregate_permutation_importances(df, features, folds)
    # pick top K
    K = 50
    topk = [f for f,_ in sorted_feats[:K]]
    print('Top features selected:', topk[:10])
    best_model, scaler, final_r2, final_mae, best_params = final_tune_and_eval(df, topk, random_search_iters=30)
    metrics = {'winsor_low': low, 'winsor_high': high, 'topK': K, 'final_r2': final_r2, 'final_mae': final_mae, 'best_params': best_params}
    save_model_and_metrics(best_model, scaler, metrics)
    print('\nFinal R2:', final_r2, 'MAE:', final_mae)
    print('Best params:', best_params)


if __name__ == '__main__':
    main()
