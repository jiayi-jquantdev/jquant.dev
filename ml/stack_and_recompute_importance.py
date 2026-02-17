#!/usr/bin/env python3
"""Replay CV, fix coverage, recompute permutation importances, and train stacking meta-model.

Outputs:
- ml/models/cv_concat_predictions.npz (preds, y, features)
- ml/models/perm_importances.json
- ml/models/stacked_model.pkl and metrics in ml/models/stacked_metrics.json
"""
import os
import json
import numpy as np
import pandas as pd

from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.linear_model import Ridge
from sklearn.inspection import permutation_importance


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


def build_folds(df, train_years=3, min_train=200, min_test=100):
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].unique())
    folds = []
    for start in range(0, len(years)-train_years):
        train_years_range = years[start:start+train_years]
        test_year = years[start+train_years]
        train_idx = df[df['year'].isin(train_years_range)].index
        test_idx = df[df['year']==test_year].index
        if len(train_idx) < min_train or len(test_idx) < min_test:
            continue
        folds.append({'train_idx':train_idx.tolist(), 'test_idx':test_idx.tolist(), 'train_years':train_years_range, 'test_year':int(test_year)})
    return folds


def replay_ensemble(df, features, folds, seeds=[11,22,33]):
    import xgboost as xgb
    preds_lists = []
    ys_lists = []
    test_X_list = []
    for fold in folds:
        train_idx = fold['train_idx']
        test_idx = fold['test_idx']
        train = df.loc[train_idx]
        test = df.loc[test_idx]
        X_tr = train[features].replace([np.inf,-np.inf], np.nan).fillna(0)
        X_te = test[features].replace([np.inf,-np.inf], np.nan).fillna(0)
        # simple per-feature winsorization based on train
        for f in features:
            lo = X_tr[f].quantile(0.01)
            hi = X_tr[f].quantile(0.99)
            X_tr[f] = X_tr[f].clip(lower=lo, upper=hi)
            X_te[f] = X_te[f].clip(lower=lo, upper=hi)
        # scale
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_trs = scaler.fit_transform(X_tr)
        X_tes = scaler.transform(X_te)
        y_tr = train['target_winsor'].values
        # ensemble
        preds = np.zeros(len(X_tes))
        for s in seeds:
            model = xgb.XGBRegressor(n_estimators=600, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
            model.fit(X_trs, y_tr)
            preds += model.predict(X_tes)
        preds /= len(seeds)
        preds_lists.append(preds)
        ys_lists.append(test['target_winsor'].values)
        test_X_list.append(X_te)
    return preds_lists, ys_lists, test_X_list


def compute_feature_coverage(df, features, folds):
    coverages = {f:[] for f in features}
    for fold in folds:
        train_idx = fold['train_idx']
        train = df.loc[train_idx]
        for f in features:
            coverages[f].append(float(train[f].notna().mean()))
    avg_coverage = {f: float(np.mean(v)) if len(v)>0 else 0.0 for f,v in coverages.items()}
    return avg_coverage


def filter_features_by_coverage(df, features, folds, min_cov=0.5):
    cov = compute_feature_coverage(df, features, folds)
    kept = [f for f in features if cov.get(f,0.0) >= min_cov]
    dropped = [f for f in features if f not in kept]
    return kept, dropped, cov


def train_permutation_on_concat(df, features, preds_lists, ys_lists, test_X_list, folds):
    # concat
    X_concat = pd.concat([pd.DataFrame(x, columns=features) for x in test_X_list], ignore_index=True)
    y_concat = np.concatenate(ys_lists)
    # train a model on data excluding all test rows
    all_test_idx = set([i for fold in folds for i in fold['test_idx']])
    train_df = df.loc[~df.index.isin(all_test_idx)]
    train_df = train_df.dropna(subset=['target_winsor'])
    X_train = train_df[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    if len(train_df) == 0:
        raise SystemExit('No training rows available for permutation importance')
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


def train_stacker_and_eval(df, features, preds_lists, ys_lists, test_X_list, final_test_features):
    # concatenated OOF for meta-training
    oof_preds = np.concatenate(preds_lists)
    y_oof = np.concatenate(ys_lists)
    feat_df = pd.concat([pd.DataFrame(x, columns=features) for x in test_X_list], ignore_index=True)
    top_feats = features[:10] if len(features)>=10 else features
    # scale oof predictions and top features for stable stacking
    from sklearn.preprocessing import StandardScaler
    pred_scaler = StandardScaler().fit(oof_preds.reshape(-1,1))
    feat_scaler = StandardScaler().fit(feat_df[top_feats].fillna(0).values)
    X_meta = np.hstack([pred_scaler.transform(oof_preds.reshape(-1,1)), feat_scaler.transform(feat_df[top_feats].fillna(0).values)])
    stacker = Ridge(alpha=1.0)
    stacker.fit(X_meta, y_oof)
    # evaluate on final year
    X_final = final_test_features[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    import xgboost as xgb
    seeds=[11,22,33]
    preds_final = np.zeros(len(X_final))
    train_mask = df['snapshot_date'].dt.year < df['snapshot_date'].dt.year.max()
    train_df = df[train_mask]
    train_df = train_df.dropna(subset=['target_winsor'])
    if len(train_df) == 0:
        raise SystemExit('No pre-final training rows available for ensemble training')
    X_train = train_df[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_final_s = scaler.transform(X_final)
    for s in seeds:
        model = xgboost = __import__('xgboost').XGBRegressor(n_estimators=800, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
        model.fit(X_train_s, train_df['target_winsor'].values)
        preds_final += model.predict(X_final_s)
    preds_final /= len(seeds)
    preds_final_scaled = pred_scaler.transform(preds_final.reshape(-1,1))
    final_feats_scaled = feat_scaler.transform(X_final[top_feats].fillna(0).values)
    final_meta = np.hstack([preds_final_scaled, final_feats_scaled])
    y_final = final_test_features['target_winsor'].values
    y_pred_final = stacker.predict(final_meta)
    r2f = r2_score(y_final, y_pred_final) if len(y_final)>1 and np.unique(y_final).shape[0]>1 else 0.0
    maef = mean_absolute_error(y_final, y_pred_final) if len(y_final)>0 else float('nan')
    return stacker, r2f, maef, preds_final, y_final


if __name__ == '__main__':
    input_csv = os.getenv('TRAIN_INPUT','ml/data/historical_snapshots_1000_v3_expanded.csv')
    df = load_data(input_csv)
    df, low, high = winsorize_target(df, 'forward_6m_return')
    df = fix_leakage_by_lagging(df)
    df = make_engineered_features(df)
    folds = build_folds(df)
    features = select_top_variance_features(df, K=150)
    print('Initial features:', len(features), 'folds:', len(folds))
    kept, dropped, cov = filter_features_by_coverage(df, features, folds, min_cov=0.5)
    print('Kept features after coverage filter:', len(kept), 'dropped:', len(dropped))
    preds_lists, ys_lists, test_X_list = replay_ensemble(df, kept, folds)
    sorted_imp, perm_model, perm_scaler, X_concat, y_concat = train_permutation_on_concat(df, kept, preds_lists, ys_lists, test_X_list, folds)
    os.makedirs('ml/models', exist_ok=True)
    with open('ml/models/perm_importances.json','w') as f:
        json.dump(sorted_imp[:200], f, indent=2)
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    final_year = int(df['snapshot_date'].dt.year.max())
    final_test_features = df[df['snapshot_date'].dt.year == final_year]
    stacker, r2f, maef, preds_final, y_final = train_stacker_and_eval(df, kept, preds_lists, ys_lists, test_X_list, final_test_features)
    print('Stacker final R2:', r2f, 'MAE:', maef)
    import joblib
    joblib.dump(stacker, 'ml/models/stacked_model.pkl')
    metrics = {'stacker_final_r2': r2f, 'stacker_final_mae': maef, 'kept_features_count': len(kept)}
    with open('ml/models/stacked_metrics.json','w') as f:
        json.dump(metrics, f, indent=2)
    # save per-fold predictions as JSON (lists) to avoid heterogeneous ndarray issues
    preds_out = {'preds': [p.tolist() for p in preds_lists], 'ys': [y.tolist() for y in ys_lists]}
    with open('ml/models/cv_concat_predictions.json','w') as f:
        json.dump(preds_out, f)
    print('Saved artifacts: perm_importances.json, stacked_model.pkl, stacked_metrics.json, cv_concat_predictions.npz')
