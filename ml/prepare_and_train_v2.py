#!/usr/bin/env python3
"""Prepare features (growth rates, ratios, quality scores), filter/impute by sector,
split by date (train: 2019-01-01..2023-12-31, test: 2024-01-01..2025-12-31),
train XGBoost and report MAE/R2.
"""
import os
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.pipeline import make_pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.metrics import r2_score, mean_absolute_error
from xgboost import XGBRegressor
import joblib

INPUT = 'ml/data/historical_snapshots_1000_v2.csv'
MODEL_OUT = 'ml/models/snapshot_xgb_v2.pkl'


def load_df(path=INPUT):
    df = pd.read_csv(path)
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    df = df.sort_values(['ticker','snapshot_date'])
    return df


def add_growth_and_ratios(df):
    # compute qoq (lag1) and yoy (lag4 approx quarterly) growth for revenue and netIncome
    df[['rev_lag1','rev_lag4','ni_lag1','ni_lag4']] = np.nan
    grp = df.groupby('ticker')
    out_rows = []
    for t, g in grp:
        g = g.sort_values('snapshot_date').copy()
        g['rev_lag1'] = g['totalRevenue'].shift(1)
        g['rev_lag4'] = g['totalRevenue'].shift(4)
        g['ni_lag1'] = g['netIncome'].shift(1)
        g['ni_lag4'] = g['netIncome'].shift(4)
        out_rows.append(g)
    df2 = pd.concat(out_rows, ignore_index=True)

    def pct_change(cur, prev):
        return (cur - prev) / prev if pd.notna(prev) and prev != 0 else np.nan

    df2['rev_qoq'] = df2.apply(lambda r: pct_change(r['totalRevenue'], r['rev_lag1']), axis=1)
    df2['rev_yoy'] = df2.apply(lambda r: pct_change(r['totalRevenue'], r['rev_lag4']), axis=1)
    df2['ni_qoq'] = df2.apply(lambda r: pct_change(r['netIncome'], r['ni_lag1']), axis=1)
    df2['ni_yoy'] = df2.apply(lambda r: pct_change(r['netIncome'], r['ni_lag4']), axis=1)

    # basic ratios and quality metrics
    df2['profit_margin'] = df2['netIncome'] / df2['totalRevenue']
    df2['debt_ratio'] = df2['totalLiabilities'] / df2['totalAssets']
    df2['roa'] = df2['netIncome'] / df2['totalAssets']
    df2['ocf_to_assets'] = df2['operatingCashflow'] / df2['totalAssets']
    # quality score (simple weighted sum)
    df2['quality_score'] = ( (df2['roa'].fillna(0) * 2.0) + (df2['profit_margin'].fillna(0) * 1.5) + (df2['ocf_to_assets'].fillna(0) * 1.0) - (df2['debt_ratio'].fillna(0) * 1.0) )

    return df2


def drop_high_missing(df, fundamentals):
    # drop rows with >30% missing among fundamentals
    num = len(fundamentals)
    df['missing_cnt'] = df[fundamentals].isna().sum(axis=1)
    df = df[df['missing_cnt'] / num <= 0.3].copy()
    df.drop(columns=['missing_cnt'], inplace=True)
    return df


def impute_by_sector(df, imputecols):
    # compute sector medians
    sector_medians = df.groupby('sector')[imputecols].median()
    # fallback global median
    global_median = df[imputecols].median()

    def fill_row(r):
        sec = r['sector']
        if pd.isna(sec) or sec not in sector_medians.index:
            for c in imputecols:
                if pd.isna(r[c]):
                    r[c] = global_median[c]
            return r
        med = sector_medians.loc[sec]
        for c in imputecols:
            if pd.isna(r[c]):
                r[c] = med[c] if pd.notna(med[c]) else global_median[c]
        return r

    df = df.apply(fill_row, axis=1)
    return df


def prepare_Xy(df):
    # features to use
    features = ['totalRevenue','netIncome','totalAssets','totalLiabilities','operatingCashflow','price_at_snapshot',
                'rev_qoq','rev_yoy','ni_qoq','ni_yoy','profit_margin','debt_ratio','roa','ocf_to_assets','quality_score']
    cat = ['sector']
    # ensure columns exist
    for f in features:
        if f not in df.columns:
            df[f] = np.nan
    X = df[features + cat].copy()
    y = df['forward_6m_return'].copy()
    return X, y, features, cat


def split_dates(df):
    train_mask = (df['snapshot_date'] >= '2019-01-01') & (df['snapshot_date'] <= '2023-12-31')
    test_mask = (df['snapshot_date'] >= '2024-01-01') & (df['snapshot_date'] <= '2025-12-31')
    return df[train_mask].copy(), df[test_mask].copy()


def train_and_eval(X_train, y_train, X_test, y_test, features, cat):
    numeric_transformer = make_pipeline(SimpleImputer(strategy='median'), StandardScaler())
    preprocessor = ColumnTransformer([('num', numeric_transformer, features), ('cat', OneHotEncoder(handle_unknown='ignore'), cat)])
    model = XGBRegressor(n_estimators=300, learning_rate=0.05, random_state=42, n_jobs=4)
    pipe = make_pipeline(preprocessor, model)
    pipe.fit(X_train, y_train)
    preds = pipe.predict(X_test)
    r2 = r2_score(y_test, preds)
    mae = mean_absolute_error(y_test, preds)
    return pipe, r2, mae


def main():
    os.makedirs('ml/models', exist_ok=True)
    df = load_df()
    df = add_growth_and_ratios(df)
    # replace infinities introduced by ratios/zero-division
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # winsorize numeric columns to remove extreme outliers (1st-99th percentile)
    numeric_cols = ['totalRevenue','netIncome','totalAssets','totalLiabilities','operatingCashflow','price_at_snapshot',
                    'rev_qoq','rev_yoy','ni_qoq','ni_yoy','profit_margin','debt_ratio','roa','ocf_to_assets','quality_score']
    for c in numeric_cols:
        if c in df.columns:
            lo = df[c].quantile(0.01)
            hi = df[c].quantile(0.99)
            df[c] = df[c].clip(lo, hi)

    fundamentals = ['totalRevenue','netIncome','totalAssets','totalLiabilities','operatingCashflow']
    df = drop_high_missing(df, fundamentals)
    df = impute_by_sector(df, fundamentals + ['price_at_snapshot','rev_qoq','rev_yoy','ni_qoq','ni_yoy','profit_margin','debt_ratio','roa','ocf_to_assets','quality_score'])

    # drop rows with invalid target
    df = df[df['forward_6m_return'].notna()]
    df = df[np.isfinite(df['forward_6m_return'])]
    train_df, test_df = split_dates(df)
    print('train rows', len(train_df), 'test rows', len(test_df))
    if len(train_df) < 500:
        print('Warning: training rows < 500; results may be unstable')

    X_train, y_train, features, cat = prepare_Xy(train_df)
    X_test, y_test, _, _ = prepare_Xy(test_df)

    pipe, r2, mae = train_and_eval(X_train, y_train, X_test, y_test, features, cat)
    print('MAE:', mae)
    print('R2:', r2)

    # extract feature importances
    try:
        # pipeline steps: ColumnTransformer then XGBRegressor
        preproc = pipe.named_steps.get('columntransformer') or pipe.named_steps.get('columntransformer')
        model = pipe.named_steps[list(pipe.named_steps.keys())[-1]]
        # numeric feature names
        num_feats = features
        # categorical one-hot names
        cat_feats = []
        try:
            ohe = preproc.named_transformers_['cat']
            cat_feats = list(ohe.get_feature_names_out(cat))
        except Exception:
            # fallback: include raw cat names
            cat_feats = cat
        feat_names = num_feats + cat_feats
        importances = model.feature_importances_
        if len(importances) == len(feat_names):
            fi = sorted(zip(feat_names, importances), key=lambda x: x[1], reverse=True)
            print('Top 10 features:')
            for name, val in fi[:10]:
                print(name, val)
        else:
            print('Feature importance length mismatch:', len(importances), 'vs', len(feat_names))
    except Exception as e:
        print('Could not extract importances:', e)

    joblib.dump(pipe, MODEL_OUT)
    print('Saved model to', MODEL_OUT)


if __name__ == '__main__':
    main()
