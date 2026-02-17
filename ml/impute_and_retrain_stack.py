#!/usr/bin/env python3
"""Impute missing features (per-ticker ffill/bfill then pre-final median),
recompute concatenated CV permutation importances, retrain stacking meta-model,
and evaluate final-year R^2 without changing the core XGBoost models.
"""
import os
import json
import numpy as np
import pandas as pd

from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.linear_model import Ridge
from sklearn.inspection import permutation_importance


def load(path='ml/data/historical_snapshots_1000_v3_expanded.csv'):
    return pd.read_csv(path)


def winsorize_target(df, col='forward_6m_return'):
    vals = df[col].dropna()
    low = vals.quantile(0.01)
    high = vals.quantile(0.99)
    df = df.copy()
    df['target_winsor'] = df[col].clip(lower=low, upper=high)
    return df, float(low), float(high)


def fix_leakage_by_lagging(df):
    df = df.copy()
    suspect_substr = ['forward', 'future', 'analyst', 'estimate', 'target', 'price_+','price_plus', 'latest', 'price_vs', 'ma_', '52week', '50day', '200day', 'forwardpe']
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    if 'snapshot_date' in df.columns:
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.sort_values(['ticker','snapshot_date'])
    for c in numcols:
        lower = c.lower()
        if any(s in lower for s in suspect_substr):
            lagname = f'lag_{c}'
            df[lagname] = df.groupby('ticker')[c].shift(1)
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


def select_top_variance_features(df, K=150):
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    cand = [c for c in numcols if not c.startswith('snapshot') and c!='forward_6m_return' and c!='target_winsor']
    variances = {c: float(df[c].dropna().var()) for c in cand}
    sorted_by_var = sorted(variances.items(), key=lambda x: x[1], reverse=True)
    return [c for c,_ in sorted_by_var[:K]]


def build_folds(df, train_years=3, min_train=100, min_test=30, start_year=2019, end_year=2025):
    """Build explicit walk-forward folds restricted to start_year..end_year.
    Folds: for test_year in [2022,2023,2024,2025] build train = test_year-3..test_year-1.
    """
    df = df.copy()
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    folds = []
    for test_year in range(start_year + train_years, min(end_year, int(df['year'].max())) + 1):
        if test_year not in range(start_year + train_years, end_year + 1):
            continue
        train_years_range = [test_year - train_years + i for i in range(train_years)]
        train_idx = df[df['year'].isin(train_years_range)].index
        test_idx = df[df['year'] == test_year].index
        if len(train_idx) < min_train or len(test_idx) < min_test:
            continue
        folds.append({'train_idx': train_idx.tolist(), 'test_idx': test_idx.tolist(), 'train_years': train_years_range, 'test_year': int(test_year)})
    return folds


def impute_features(df, features, folds):
    # per-ticker forward then backward fill
    df = df.copy()
    df = df.sort_values(['ticker','snapshot_date'])
    # Only forward-fill (use past values) to avoid leaking future data via bfill.
    df[features] = df.groupby('ticker')[features].ffill()
    # compute per-year pre-year medians (for year Y, use rows with year < Y)
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].dropna().unique())
    medians_by_year = {}
    for y in years:
        pre = df[df['year'] < int(y)]
        if len(pre) == 0:
            med = pd.Series({f: np.nan for f in features})
        else:
            med = pre[features].median()
        medians_by_year[int(y)] = med
    # fill remaining NaNs for each row using medians from prior years only
    for y in years:
        mask = df['year'] == int(y)
        med = medians_by_year.get(int(y))
        if med is None:
            continue
        for f in features:
            m = med.get(f, np.nan)
            if np.isfinite(m):
                df.loc[mask, f] = df.loc[mask, f].fillna(m)
    # For any remaining NaNs (earliest years with no prior medians), fill with global median
    global_pre = df[df['year'] < df['year'].max()]
    global_meds = global_pre[features].median()
    for f in features:
        gm = global_meds.get(f, np.nan)
        if np.isfinite(gm):
            df[f] = df[f].fillna(gm)
    return df, {y: medians_by_year[y].to_dict() for y in medians_by_year}


def replay_ensemble_collect(df, features, folds, seeds=[11,22,33]):
    import xgboost as xgb
    preds_lists = []
    ys_lists = []
    test_X_list = []
    per_fold_metrics = []
    for fold in folds:
        train_idx = fold['train_idx']
        test_idx = fold['test_idx']
        train = df.loc[train_idx]
        test = df.loc[test_idx]
        # winsorize & clip based on train
        # filter features by coverage in this fold's training data to avoid using
        # features that appear only in later years (distributional shift)
        avail = []
        for f in features:
            cov = train[f].replace([np.inf, -np.inf], np.nan).notna().mean()
            if cov >= 0.5:
                avail.append(f)
        if len(avail) < max(10, int(0.2 * len(features))):
            avail = features
        X_tr = train[avail].replace([np.inf,-np.inf], np.nan).fillna(0)
        X_te = test[avail].replace([np.inf,-np.inf], np.nan).fillna(0)
        for f in X_tr.columns:
            lo = X_tr[f].quantile(0.01)
            hi = X_tr[f].quantile(0.99)
            X_tr[f] = X_tr[f].clip(lower=lo, upper=hi)
            if f in X_te.columns:
                X_te[f] = X_te[f].clip(lower=lo, upper=hi)
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_trs = scaler.fit_transform(X_tr)
        X_tes = scaler.transform(X_te)
        y_tr = train['target_winsor'].values
        y_te = test['target_winsor'].values
        preds = np.zeros(len(X_tes))
        for s in seeds:
            model = xgb.XGBRegressor(n_estimators=600, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
            model.fit(X_trs, y_tr)
            preds += model.predict(X_tes)
        preds /= len(seeds)
        preds_lists.append(preds)
        ys_lists.append(y_te)
        test_X_list.append(X_te)
        per_fold_metrics.append({'train_years':fold['train_years'], 'test_year':fold['test_year'], 'r2':float(r2_score(y_te, preds)), 'mae':float(mean_absolute_error(y_te, preds))})
    return preds_lists, ys_lists, test_X_list, per_fold_metrics


def compute_permutation_concat(df, features, preds_lists, ys_lists, test_X_list, folds):
    X_concat = pd.concat([pd.DataFrame(x, columns=features) for x in test_X_list], ignore_index=True)
    y_concat = np.concatenate(ys_lists)
    # train on pre-final data
    all_test_idx = set(i for fold in folds for i in fold['test_idx'])
    train_df = df.loc[~df.index.isin(all_test_idx)]
    train_df = train_df.dropna(subset=['target_winsor'])
    X_train = train_df[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    y_train = train_df['target_winsor'].values
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_concat_s = scaler.transform(X_concat.fillna(0))
    import xgboost as xgb
    model = xgb.XGBRegressor(n_estimators=800, max_depth=6, learning_rate=0.03, random_state=42, verbosity=0, subsample=0.8, colsample_bytree=0.8)
    model.fit(X_train_s, y_train)
    perm = permutation_importance(model, X_concat_s, y_concat, n_repeats=10, random_state=42, n_jobs=4)
    importances = {feat: float(perm.importances_mean[i]) for i,feat in enumerate(features)}
    sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    return sorted_imp, model, scaler, X_concat, y_concat


def train_stacker(df, features, preds_lists, ys_lists, test_X_list, final_year):
    # build meta X (oof preds) and train ridge
    oof_preds = np.concatenate(preds_lists)
    y_oof = np.concatenate(ys_lists)
    feat_df = pd.concat([pd.DataFrame(x, columns=features) for x in test_X_list], ignore_index=True)
    top_feats = features[:10] if len(features)>=10 else features
    from sklearn.preprocessing import StandardScaler
    pred_scaler = StandardScaler().fit(oof_preds.reshape(-1,1))
    feat_scaler = StandardScaler().fit(feat_df[top_feats].fillna(0).values)
    X_meta = np.hstack([pred_scaler.transform(oof_preds.reshape(-1,1)), feat_scaler.transform(feat_df[top_feats].fillna(0).values)])
    stacker = Ridge(alpha=1.0)
    stacker.fit(X_meta, y_oof)
    # final-year ensemble preds
    train_mask = df['snapshot_date'].dt.year < final_year
    train_df = df[train_mask].dropna(subset=['target_winsor'])
    X_train = train_df[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    scaler = StandardScaler().fit(X_train)
    X_final = df[df['snapshot_date'].dt.year==final_year][features].replace([np.inf,-np.inf], np.nan).fillna(0)
    X_final_s = scaler.transform(X_final)
    import xgboost as xgb
    seeds=[11,22,33]
    preds_final = np.zeros(len(X_final_s))
    for s in seeds:
        m = xgboost = __import__('xgboost').XGBRegressor(n_estimators=800, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
        m.fit(scaler.transform(X_train), train_df['target_winsor'].values)
        preds_final += m.predict(X_final_s)
    preds_final /= len(seeds)
    preds_final_scaled = pred_scaler.transform(preds_final.reshape(-1,1))
    final_feats_scaled = feat_scaler.transform(X_final[top_feats].fillna(0).values)
    final_meta = np.hstack([preds_final_scaled, final_feats_scaled])
    y_final = df[df['snapshot_date'].dt.year==final_year]['target_winsor'].values
    y_pred_final = stacker.predict(final_meta)
    r2f = r2_score(y_final, y_pred_final) if len(y_final)>1 and np.unique(y_final).shape[0]>1 else 0.0
    maef = mean_absolute_error(y_final, y_pred_final) if len(y_final)>0 else float('nan')
    return stacker, r2f, maef, preds_final, y_final


if __name__ == '__main__':
    df = load()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df, low, high = winsorize_target(df)
    df = fix_leakage_by_lagging(df)
    df = make_engineered_features(df)
    # select candidates by variance, then filter to stable features across 2019-2025
    features = select_top_variance_features(df, K=150)
    # compute coverage in 2019-2025
    df['year'] = df['snapshot_date'].dt.year
    recent_mask = df['year'].between(2019, 2025)
    recent = df[recent_mask]
    coverage = {}
    for f in features:
        coverage[f] = float(recent[f].notna().mean()) if f in recent.columns else 0.0
    stable_features = [f for f,v in coverage.items() if v >= 0.8]
    if len(stable_features) == 0:
        stable_features = features
    print('Features selected by variance:', len(features), 'Stable features (80% coverage 2019-2025):', len(stable_features))
    features = stable_features
    folds = build_folds(df, start_year=2019, end_year=2025)
    print('Selected features:', len(features), 'folds:', len(folds))
    # impute
    df_imputed, medians = impute_features(df, features, folds)
    print('Imputation medians sample:', {k:medians[k] for k in list(medians)[:5]})
    preds_lists, ys_lists, test_X_list, per_fold_metrics = replay_ensemble_collect(df_imputed, features, folds)
    print('Per-fold metrics:')
    for m in per_fold_metrics:
        print(m)
    sorted_imp, model, scaler, X_concat, y_concat = compute_permutation_concat(df_imputed, features, preds_lists, ys_lists, test_X_list, folds)
    os.makedirs('ml/models', exist_ok=True)
    with open('ml/models/perm_importances_recomputed.json','w') as f:
        json.dump(sorted_imp[:200], f, indent=2)
    final_year = int(df_imputed['snapshot_date'].dt.year.max())
    stacker, r2f, maef, preds_final, y_final = train_stacker(df_imputed, features, preds_lists, ys_lists, test_X_list, final_year)
    print('Stacker final R2:', r2f, 'MAE:', maef)
    import joblib
    joblib.dump(stacker, 'ml/models/stacked_model_imputed.pkl')
    metrics = {'final_r2': r2f, 'final_mae': maef, 'kept_features': len(features)}
    with open('ml/models/stacked_metrics_imputed.json','w') as f:
        json.dump(metrics, f, indent=2)
    # save per-fold preds
    preds_out = {'preds': [p.tolist() for p in preds_lists], 'ys': [y.tolist() for y in ys_lists]}
    with open('ml/models/cv_predictions_imputed.json','w') as f:
        json.dump(preds_out, f)
    print('Saved: perm_importances_recomputed.json, stacked_model_imputed.pkl, stacked_metrics_imputed.json, cv_predictions_imputed.json')
