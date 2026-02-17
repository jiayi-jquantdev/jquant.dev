#!/usr/bin/env python3
"""Prepare training data from historical snapshots and train an XGBoost model.

Splits: train = snapshots with snapshot_date in 2019-01-01..2022-12-31
        test  = snapshots with snapshot_date in 2023-01-01..2024-12-31
"""
import os
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.pipeline import make_pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.metrics import r2_score, mean_absolute_error
from xgboost import XGBRegressor
import joblib

INPUT = "ml/data/historical_snapshots_1000_clean.csv"
MODEL_OUT = "ml/models/snapshot_xgb.pkl"


def load_data(path=INPUT):
    df = pd.read_csv(path)
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date'], errors='coerce')
    # drop rows without target
    df = df[df['forward_6m_return'].notna()]
    return df


def prepare_features(df):
    # numeric features
    num_cols = ['totalRevenue','netIncome','totalAssets','totalLiabilities','operatingCashflow','price_at_snapshot']
    # include sector as categorical
    cat_cols = ['sector']
    X_num = df[num_cols].copy()
    # impute numeric with median
    X_num = X_num.fillna(X_num.median())
    X_cat = df[cat_cols].fillna('Unknown')
    return X_num, X_cat, num_cols, cat_cols


def split_by_date(df):
    train_mask = (df['snapshot_date'] >= '2019-01-01') & (df['snapshot_date'] <= '2022-12-31')
    test_mask = (df['snapshot_date'] >= '2023-01-01') & (df['snapshot_date'] <= '2024-12-31')
    return df[train_mask].copy(), df[test_mask].copy()


def main():
    os.makedirs('ml/models', exist_ok=True)
    df = load_data()
    train_df, test_df = split_by_date(df)
    print('train rows', len(train_df), 'test rows', len(test_df))
    if len(train_df) < 50 or len(test_df) < 10:
        print('Not enough data for requested splits; aborting')
        return

    Xn_train, Xc_train, num_cols, cat_cols = prepare_features(train_df)
    Xn_test, Xc_test, _, _ = prepare_features(test_df)
    # build preprocessing + model pipeline
    numeric_transformer = make_pipeline(SimpleImputer(strategy='median'), StandardScaler())
    preprocessor = ColumnTransformer([('num', numeric_transformer, num_cols), ('cat', OneHotEncoder(handle_unknown='ignore'), cat_cols)])

    model = XGBRegressor(n_estimators=200, learning_rate=0.05, random_state=42, n_jobs=4)
    pipe = make_pipeline(preprocessor, model)

    X_train = pd.concat([Xn_train, Xc_train], axis=1)
    X_test = pd.concat([Xn_test, Xc_test], axis=1)
    y_train = train_df['forward_6m_return']
    y_test = test_df['forward_6m_return']

    pipe.fit(X_train, y_train)
    preds = pipe.predict(X_test)
    r2 = r2_score(y_test, preds)
    mae = mean_absolute_error(y_test, preds)
    print('MAE:', mae)
    print('R2:', r2)

    joblib.dump(pipe, MODEL_OUT)
    print('Saved model to', MODEL_OUT)


if __name__ == '__main__':
    main()
