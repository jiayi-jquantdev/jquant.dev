#!/usr/bin/env python3
"""
Train an XGBoost regression model on ml/data/training_data.csv
Saves model to ml/models/stock_predictor.pkl
"""
import os
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
MODELS_DIR = ROOT / 'models'
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_CSV = DATA_DIR / 'training_data.csv'
MODEL_PKL = MODELS_DIR / 'stock_predictor.pkl'
FEATURES_JSON = MODELS_DIR / 'feature_names.json'
METRICS_JSON = MODELS_DIR / 'metrics.json'

def load_data():
    if not TRAIN_CSV.exists():
        raise FileNotFoundError(f'{TRAIN_CSV} not found. Run calculate_returns.py first')
    df = pd.read_csv(TRAIN_CSV)
    return df

def prepare_features(df: pd.DataFrame):
    # Drop obvious non-feature columns
    drop_cols = [c for c in ['Symbol', 'symbol', 'Ticker', 'ticker'] if c in df.columns]
    if 'return_6m' not in df.columns:
        raise ValueError('return_6m column not found in training data')
    X = df.drop(columns=[*drop_cols, 'return_6m'])
    # convert columns to numeric where possible
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')
    # simple imputation: median
    X = X.fillna(X.median(numeric_only=True))
    y = pd.to_numeric(df['return_6m'], errors='coerce').fillna(0.0)
    return X, y

def main():
    df = load_data()
    X, y = prepare_features(df)
    feature_names = list(X.columns)
    if X.shape[0] < 10:
        print('Not enough training rows; need more data')
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))
    r2 = float(r2_score(y_test, preds))

    print('MAE:', mae)
    print('R2:', r2)

    # feature importance
    try:
        importances = model.feature_importances_.tolist()
    except Exception:
        importances = []

    # Save model and metadata
    joblib.dump(model, MODEL_PKL)
    with open(FEATURES_JSON, 'w', encoding='utf8') as f:
        json.dump(feature_names, f)
    with open(METRICS_JSON, 'w', encoding='utf8') as f:
        json.dump({'mae': mae, 'r2': r2, 'feature_importances': importances}, f, indent=2)

    print(f'Model saved to {MODEL_PKL}')

if __name__ == '__main__':
    main()
