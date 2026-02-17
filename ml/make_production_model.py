#!/usr/bin/env python3
"""Build and save production model v1 trained on 2019-2025.

Outputs:
- ml/models/production_model_v1.pkl (dict with ensembles, stacker, features, scalers, medians)
- prints top-20 permutation importance features and reported CV averages
"""
import os
import json
import joblib
import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error


def load_csv(path='ml/data/historical_snapshots_1000_v3_expanded.csv'):
    return pd.read_csv(path)


def preprocess(df):
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    # winsorize target
    vals = df['forward_6m_return'].dropna()
    low = vals.quantile(0.01)
    high = vals.quantile(0.99)
    df['target_winsor'] = df['forward_6m_return'].clip(lower=low, upper=high)
    # leakage lagging
    suspect = ['forward','future','analyst','estimate','target','price_+','price_plus','latest','price_vs','ma_','52week','50day','200day','forwardpe']
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    df = df.sort_values(['ticker','snapshot_date'])
    for c in numcols:
        cl = c.lower()
        if any(s in cl for s in suspect):
            df[f'lag_{c}'] = df.groupby('ticker')[c].shift(1)
    # trailing pe
    if 'price_at_snapshot' in df.columns and 'eps_ttm' in df.columns:
        df['pe_trailing'] = df['price_at_snapshot'] / df['eps_ttm']
    # engineered features (minimal)
    for col in ['overview_MarketCapitalization','overview_SharesOutstanding','totalAssets','totalLiabilities']:
        if col in df.columns:
            df[f'log_{col}'] = np.log1p(df[col].where(df[col]>0, 0))
    return df, low, high


def select_features(df, K=150):
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    cand = [c for c in numcols if not c.startswith('snapshot') and c not in ('forward_6m_return','target_winsor')]
    variances = {c: float(df[c].dropna().var()) for c in cand}
    sorted_by_var = sorted(variances.items(), key=lambda x: x[1], reverse=True)
    return [c for c,_ in sorted_by_var[:K]]


def impute(df, features):
    df = df.sort_values(['ticker','snapshot_date'])
    df[features] = df.groupby('ticker')[features].ffill()
    df[features] = df.groupby('ticker')[features].bfill()
    df['year'] = df['snapshot_date'].dt.year
    final_year = int(df['year'].max())
    pre_final = df[df['year'] < final_year]
    medians = pre_final[features].median()
    for f in features:
        m = medians.get(f, np.nan)
        if np.isfinite(m):
            df[f] = df[f].fillna(m)
    return df, medians.to_dict(), final_year


def build_folds(df, train_years=3):
    df = df.dropna(subset=['snapshot_date','target_winsor']).copy()
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].unique())
    folds = []
    for start in range(0, len(years)-train_years):
        train_years_range = years[start:start+train_years]
        test_year = years[start+train_years]
        train_idx = df[df['year'].isin(train_years_range)].index
        test_idx = df[df['year']==test_year].index
        folds.append({'train_idx':train_idx.tolist(),'test_idx':test_idx.tolist(),'test_year':int(test_year)})
    return folds


def ensemble_preds_on_fold(df, features, train_idx, test_idx, seeds=[11,22,33]):
    import xgboost as xgb
    train = df.loc[train_idx]
    test = df.loc[test_idx]
    # drop any rows with missing target in train
    train = train.dropna(subset=['target_winsor'])
    X_tr = train[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    X_te = test[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    for f in features:
        lo = X_tr[f].quantile(0.01)
        hi = X_tr[f].quantile(0.99)
        X_tr[f] = X_tr[f].clip(lower=lo, upper=hi)
        X_te[f] = X_te[f].clip(lower=lo, upper=hi)
    scaler = StandardScaler().fit(X_tr)
    X_trs = scaler.transform(X_tr)
    X_tes = scaler.transform(X_te)
    preds = np.zeros(len(X_tes))
    for s in seeds:
        m = xgb.XGBRegressor(n_estimators=600, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
        m.fit(X_trs, train['target_winsor'].values)
        preds += m.predict(X_tes)
    preds /= len(seeds)
    return preds


def train_production_ensemble(df, features, final_train_year):
    import xgboost as xgb
    train_df = df[df['snapshot_date'].dt.year <= final_train_year]
    train_df = train_df.dropna(subset=['target_winsor'])
    X = train_df[features].replace([np.inf,-np.inf], np.nan).fillna(0)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    y = train_df['target_winsor'].values
    models = []
    seeds=[11,22,33]
    for s in seeds:
        m = xgb.XGBRegressor(n_estimators=800, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
        m.fit(Xs, y)
        models.append(m)
    return models, scaler


def main():
    df = load_csv()
    df, low, high = preprocess(df)
    features = select_features(df, K=150)
    df_imputed, medians, final_year = impute(df, features)
    # Build folds and compute per-fold metrics excluding final year (incomplete)
    folds = build_folds(df_imputed, train_years=3)
    valid_folds = [f for f in folds if f['test_year'] < final_year]
    per_fold = []
    for f in valid_folds:
        preds = ensemble_preds_on_fold(df_imputed, features, f['train_idx'], f['test_idx'])
        y = df_imputed.loc[f['test_idx']]['target_winsor'].values
        per_fold.append({'test_year':f['test_year'], 'r2':float(r2_score(y, preds)), 'mae':float(mean_absolute_error(y, preds))})
    r2s = [p['r2'] for p in per_fold]
    maes = [p['mae'] for p in per_fold]
    avg_r2 = float(np.mean(r2s)) if r2s else None
    avg_mae = float(np.mean(maes)) if maes else None

    # train production ensemble on 2019-2025 (<= final_year-1)
    final_train_year = final_year - 1
    ensembles, feature_scaler = train_production_ensemble(df_imputed, features, final_train_year)

    # load stacker trained earlier (stacked_model_imputed.pkl)
    stacker_path = 'ml/models/stacked_model_imputed.pkl'
    if os.path.exists(stacker_path):
        stacker = joblib.load(stacker_path)
    else:
        stacker = None

    prod = {'ensembles': ensembles, 'stacker': stacker, 'features': features, 'top_feats': features[:10], 'feature_scaler': feature_scaler, 'medians': medians, 'winsor': {'low': low, 'high': high}}
    os.makedirs('ml/models', exist_ok=True)
    joblib.dump(prod, 'ml/models/production_model_v1.pkl')

    # top-20 features from recomputed permutation importances if available
    perm_path = 'ml/models/perm_importances_recomputed.json'
    top20 = None
    if os.path.exists(perm_path):
        with open(perm_path,'r') as f:
            perm = json.load(f)
            top20 = [t[0] for t in perm[:20]]

    print('Production model saved to ml/models/production_model_v1.pkl')
    print('CV folds (valid):')
    for p in per_fold:
        print(p)
    print('\nAverage CV R2 (valid folds):', avg_r2)
    print('Average CV MAE (valid folds):', avg_mae)
    print('\nTop 20 permutation features:')
    if top20:
        for t in top20:
            print(' -', t)
    else:
        print('perm_importances_recomputed.json not found')


if __name__ == '__main__':
    main()
