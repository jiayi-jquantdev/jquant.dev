#!/usr/bin/env python3
"""Feature engineering + ensemble of XGBoosts (keep core model unchanged).

Creates log/transformed, interaction, and rank features, selects top-variance
features, trains an ensemble (3 XGBoosts with different seeds) with rolling
walk-forward CV, then trains final ensemble and reports metrics.
"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
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
    # log transforms for positive-valued overviews
    for col in ['overview_MarketCapitalization','overview_SharesOutstanding','totalAssets','totalLiabilities']:
        if col in df.columns:
            df[f'log_{col}'] = np.log1p(df[col].where(df[col]>0, 0))
    # momentum and valuation interactions
    momentum = [c for c in ['r1m','r3m','r6m','r12m'] if c in df.columns]
    valuation = [c for c in ['pe_trailing','pb','pe_vs_sector','pb_vs_sector','pe_mean_by_stock'] if c in df.columns]
    for m in momentum:
        for v in valuation:
            df[f'{m}_x_{v}'] = df[m].fillna(0) * df[v].fillna(0)
    # rank features within each snapshot_date (preserves no-forward leakage)
    if 'snapshot_date' in df.columns:
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
        rank_cols = momentum + valuation
        for c in rank_cols:
            if c in df.columns:
                df[f'rank_{c}'] = df.groupby('snapshot_date')[c].rank(pct=True)
    # create volatility proxy from r1m/r3m if available
    if 'r1m' in df.columns and 'r3m' in df.columns:
        df['mom_std_proxy'] = df[['r1m','r3m']].std(axis=1)
    return df


def select_top_variance_features(df, exclude=set(['forward_6m_return','target_winsor'])):
    numcols = df.select_dtypes(include=[np.number]).columns.tolist()
    cand = [c for c in numcols if c not in exclude and not c.startswith('snapshot')]
    variances = {c: float(df[c].dropna().var()) for c in cand}
    sorted_by_var = sorted(variances.items(), key=lambda x: x[1], reverse=True)
    K = 150
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
    scaler = StandardScaler()
    X_trs = scaler.fit_transform(X_tr)
    X_tes = scaler.transform(X_te)
    return X_trs, X_tes, scaler


def rolling_ensemble_cv(df, features, seeds=[1,2,3], train_years=3, min_train=200, min_test=100):
    import xgboost as xgb
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].unique())
    folds = []
    fold_metrics = []
    preds_concat = []
    y_concat = []
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
        # ensemble average of same core model
        preds = np.zeros(len(y_te))
        for s in seeds:
            model = xgb.XGBRegressor(n_estimators=600, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
            model.fit(X_trs, y_tr)
            preds += model.predict(X_tes)
        preds /= len(seeds)
        r2 = float(r2_score(y_te, preds))
        mae = float(mean_absolute_error(y_te, preds))
        fold_metrics.append({'train_years':train_years_range, 'test_year':test_year, 'r2':r2, 'mae':mae, 'n_train':len(train), 'n_test':len(test)})
        preds_concat.append(preds)
        y_concat.append(y_te)
        print(f"Fold {train_years_range} -> {test_year} R2={r2:.4f} MAE={mae:.4f}")
    if preds_concat:
        y_all = np.concatenate(y_concat)
        preds_all = np.concatenate(preds_concat)
        agg_r2 = float(r2_score(y_all, preds_all))
        agg_mae = float(mean_absolute_error(y_all, preds_all))
    else:
        agg_r2 = None
        agg_mae = None
    return fold_metrics, agg_r2, agg_mae


def final_ensemble_train(df, features, seeds=[1,2,3]):
    import xgboost as xgb
    df = df.copy()
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.dropna(subset=['snapshot_date','target_winsor'])
    df['year'] = df['snapshot_date'].dt.year
    years = sorted(df['year'].unique())
    train = df[df['year'] < years[-1]]
    test = df[df['year'] == years[-1]]
    X_trs, X_tes, scaler = sanitize_and_scale(train, test, features)
    y_tr = train['target_winsor'].values
    y_te = test['target_winsor'].values
    models = []
    preds = np.zeros(len(y_te)) if len(y_te)>0 else np.array([])
    for s in seeds:
        model = xgb.XGBRegressor(n_estimators=800, max_depth=6, learning_rate=0.03, random_state=s, verbosity=0, subsample=0.8, colsample_bytree=0.8)
        model.fit(X_trs, y_tr)
        models.append(model)
        if len(y_te)>0:
            preds += model.predict(X_tes)
    if len(y_te)>0:
        preds /= len(models)
        r2f = float(r2_score(y_te, preds))
        maef = float(mean_absolute_error(y_te, preds))
    else:
        r2f = 0.0
        maef = float('nan')
    return models, scaler, r2f, maef


def save_models(models, scaler, metrics, model_dir='ml/models', prefix='snapshot_xgb_ensemble'):
    os.makedirs(model_dir, exist_ok=True)
    import joblib
    for i,m in enumerate(models):
        joblib.dump(m, os.path.join(model_dir, f'{prefix}_m{i}.pkl'))
    joblib.dump(scaler, os.path.join(model_dir, f'{prefix}_scaler.pkl'))
    with open(os.path.join(model_dir, f'{prefix}_metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)


def main():
    input_csv = os.getenv('TRAIN_INPUT','ml/data/historical_snapshots_1000_v3_expanded.csv')
    df = load_data(input_csv)
    df, low, high = winsorize_target(df, 'forward_6m_return')
    df = fix_leakage_by_lagging(df)
    df = make_engineered_features(df)
    topk = select_top_variance_features(df)
    print('Selected top features:', len(topk))
    folds, agg_r2, agg_mae = rolling_ensemble_cv(df, topk, seeds=[11,22,33])
    print('Aggregated CV R2:', agg_r2, 'MAE:', agg_mae)
    models, scaler, final_r2, final_mae = final_ensemble_train(df, topk, seeds=[11,22,33])
    metrics = {'winsor_low': low, 'winsor_high': high, 'agg_cv_r2': agg_r2, 'agg_cv_mae': agg_mae, 'final_r2': final_r2, 'final_mae': final_mae, 'feature_count': len(topk)}
    save_models(models, scaler, metrics)
    print('\nFinal ensemble R2:', final_r2, 'MAE:', final_mae)


if __name__ == '__main__':
    main()
