#!/usr/bin/env python3
"""Replay ensemble CV and run diagnostics to validate aggregated R^2 authenticity.

Prints per-fold R2/MAE, prediction variance checks, correlation with target,
aggregated R2/MAE across folds, and simple distribution-shift stats.
Saves per-fold predictions to `ml/models/cv_predictions.csv`.
"""
import os
import csv
import json
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_absolute_error


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
    df = df.sort_values(['ticker','snapshot_date'])
    for c in numcols:
        lower = c.lower()
        if any(s in lower for s in suspect_substr):
            lagname = f'lag_{c}'
            try:
                df[lagname] = df.groupby('ticker')[c].shift(1)
            except Exception:
                df[lagname] = np.nan
    if 'price_at_snapshot' in df.columns and 'eps_ttm' in df.columns:
        with np.errstate(divide='ignore', invalid='ignore'):
            df['pe_trailing'] = df['price_at_snapshot'] / df['eps_ttm']
    return df


def make_engineered_features(df):
    df = df.copy()
    for col in ['overview_MarketCapitalization','overview_SharesOutstanding','totalAssets','totalLiabilities']:
        if col in df.columns:
            df[f'log_{col}'] = np.log1p(df[col].where(df[col]>0, 0))
    momentum = [c for c in ['r1m','r3m','r6m','r12m'] if c in df.columns]
    valuation = [c for c in ['pe_trailing','pb','pe_vs_sector','pb_vs_sector','pe_mean_by_stock'] if c in df.columns]
    for m in momentum:
        for v in valuation:
            df[f'{m}_x_{v}'] = df[m].fillna(0) * df[v].fillna(0)
    if 'snapshot_date' in df.columns:
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
        rank_cols = momentum + valuation
        for c in rank_cols:
            if c in df.columns:
                df[f'rank_{c}'] = df.groupby('snapshot_date')[c].rank(pct=True)
    if 'r1m' in df.columns and 'r3m' in df.columns:
        df['mom_std_proxy'] = df[['r1m','r3m']].std(axis=1)
    return df


def select_top_variance_features(df, K=150, exclude=set(['forward_6m_return','target_winsor'])):
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    cand = [c for c in numcols if c not in exclude and not c.startswith('snapshot')]
    variances = {c: float(df[c].dropna().var()) for c in cand}
    sorted_by_var = sorted(variances.items(), key=lambda x: x[1], reverse=True)
    topk = [c for c,_ in sorted_by_var[:K]]
    return topk


def sanitize_and_scale(train_df, test_df, features):
    X_tr = train_df[features].replace([np.inf, -np.inf], np.nan).fillna(0).copy()
    X_te = test_df[features].replace([np.inf, -np.inf], np.nan).fillna(0).copy()
    for f in features:
        lo = X_tr[f].quantile(0.01)
        hi = X_tr[f].quantile(0.99)
        X_tr[f] = X_tr[f].clip(lower=lo, upper=hi)
        X_te[f] = X_te[f].clip(lower=lo, upper=hi)
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_trs = scaler.fit_transform(X_tr)
    X_tes = scaler.transform(X_te)
    return X_trs, X_tes, scaler


def replay_ensemble_and_collect(df, features, seeds=[11,22,33], train_years=3, min_train=200, min_test=100):
    import xgboost as xgb
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].unique())
    per_fold_records = []
    preds_all = []
    y_all = []
    for start in range(0, len(years)-train_years):
        train_years_range = years[start:start+train_years]
        test_year = years[start+train_years]
        train = df[df['year'].isin(train_years_range)]
        test = df[df['year']==test_year]
        if len(train) < min_train or len(test) < min_test:
            continue
        X_trs, X_tes, _ = sanitize_and_scale(train, test, features)
        y_tr = train['target_winsor'].values
        y_te = test['target_winsor'].values
        preds = np.zeros(len(y_te))
        for s in seeds:
            model = xgb.XGBRegressor(n_estimators=600, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
            model.fit(X_trs, y_tr)
            preds += model.predict(X_tes)
        preds /= len(seeds)
        r2 = r2_score(y_te, preds)
        mae = mean_absolute_error(y_te, preds)
        stdp = float(np.std(preds))
        corr = float(np.corrcoef(y_te, preds)[0,1]) if np.unique(preds).shape[0]>1 and np.unique(y_te).shape[0]>1 else float('nan')
        per_fold_records.append({'train_years':train_years_range, 'test_year':test_year, 'r2':float(r2), 'mae':float(mae), 'std_pred':stdp, 'corr':corr, 'n_test':len(test)})
        preds_all.append(preds)
        y_all.append(y_te)
        print(f"Fold {train_years_range}->{test_year}: R2={r2:.4f} MAE={mae:.4f} std_pred={stdp:.6f} corr={corr:.4f} n_test={len(test)}")
    if preds_all:
        y_concat = np.concatenate(y_all)
        preds_concat = np.concatenate(preds_all)
        agg_r2 = r2_score(y_concat, preds_concat)
        agg_mae = mean_absolute_error(y_concat, preds_concat)
    else:
        agg_r2 = None
        agg_mae = None
    return per_fold_records, agg_r2, agg_mae, preds_all, y_all


def save_cv_predictions(preds_lists, ys_lists, folds, out_path='ml/models/cv_predictions.csv'):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    rows = []
    for fi,(preds, ys) in enumerate(zip(preds_lists, ys_lists)):
        for i,(p,y) in enumerate(zip(preds, ys)):
            rows.append({'fold':fi, 'pred':float(p), 'target':float(y)})
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    return out_path


def distribution_shift_checks(df, features, folds):
    results = []
    for f in folds:
        train_years = f['train_years']
        test_year = f['test_year']
        train = df[df['snapshot_date'].dt.year.isin(train_years)]
        test = df[df['snapshot_date'].dt.year==test_year]
        for feat in features[:10]:
            tr_mean = float(train[feat].dropna().mean()) if feat in train.columns else float('nan')
            te_mean = float(test[feat].dropna().mean()) if feat in test.columns else float('nan')
            results.append({'feat':feat, 'train_mean':tr_mean, 'test_mean':te_mean, 'train_years':train_years, 'test_year':test_year})
    return results


def main():
    input_csv = os.getenv('TRAIN_INPUT','ml/data/historical_snapshots_1000_v3_expanded.csv')
    df = load_data(input_csv)
    df, low, high = winsorize_target(df, 'forward_6m_return')
    df = fix_leakage_by_lagging(df)
    df = make_engineered_features(df)
    topk = select_top_variance_features(df, K=150)
    print('Using top features count:', len(topk))
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].unique())
    folds = []
    train_years=3
    for start in range(0, len(years)-train_years):
        train_years_range = years[start:start+train_years]
        test_year = years[start+train_years]
        train = df[df['year'].isin(train_years_range)]
        test = df[df['year']==test_year]
        if len(train) < 200 or len(test) < 100:
            continue
        folds.append({'train_years':train_years_range, 'test_year':test_year})
    per_fold, agg_r2, agg_mae, preds_lists, ys_lists = replay_ensemble_and_collect(df, topk, seeds=[11,22,33])
    print('\nAggregated CV R2:', agg_r2, 'MAE:', agg_mae)
    out_csv = save_cv_predictions(preds_lists, ys_lists, per_fold)
    print('Saved per-fold predictions to', out_csv)
    all_pred_stds = [np.std(p) for p in preds_lists]
    print('Per-fold prediction stds (first 5):', all_pred_stds[:5])
    near_const = sum(1 for s in all_pred_stds if s < 1e-6)
    print('Folds with near-constant predictions:', near_const, 'of', len(all_pred_stds))
    dist_checks = distribution_shift_checks(df, topk, per_fold)
    print('Sample distribution shifts for top features (first 10):')
    for r in dist_checks[:10]:
        print(r)


if __name__ == '__main__':
    main()
