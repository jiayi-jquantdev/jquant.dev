#!/usr/bin/env python3
"""
Retrain model after removing price-derived leaking features.
Attempts a time-based split using `LatestQuarter` if available; otherwise falls back to random split.
Saves model and metrics to ml/models/.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import json
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent
TRAIN_CSV = ROOT / 'data' / 'training_data.csv'
MODELS_DIR = ROOT / 'models'
MODELS_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PKL = MODELS_DIR / 'stock_predictor_no_leak.pkl'
METRICS_JSON = MODELS_DIR / 'metrics_no_leak.json'

# Columns to remove because they are price-derived
LEAK_COLS = ['latest_close', 'MarketCapitalization', '52WeekHigh', '52WeekLow', '50DayMovingAverage', '200DayMovingAverage']

def try_parse_date(s):
    try:
        return pd.to_datetime(s, errors='coerce')
    except Exception:
        return pd.NaT

def main():
    df = pd.read_csv(TRAIN_CSV)
    df.columns = [c.strip() for c in df.columns]

    # drop leak columns if present
    for c in LEAK_COLS:
        if c in df.columns:
            df = df.drop(columns=[c])

    # prepare X and y
    drop_cols = [c for c in ['Symbol','symbol','Ticker','ticker','return_6m'] if c in df.columns]
    y = pd.to_numeric(df['return_6m'], errors='coerce')
    X = df.drop(columns=drop_cols)

    # convert to numeric where possible
    for col in X.columns:
        X[col] = pd.to_numeric(X[col].replace(['', 'None', '-', 'NA'], np.nan), errors='coerce')

    # simple imputation
    X = X.fillna(X.median(numeric_only=True))

    # Attempt time-based split using LatestQuarter if usable
    split_used = 'random'
    if 'LatestQuarter' in df.columns:
        dates = try_parse_date(df['LatestQuarter'])
        if dates.notna().sum() > 0:
            # compute cutoff at 80th percentile
            cutoff = dates.quantile(0.8)
            mask = dates <= cutoff
            if mask.sum() > 10 and (~mask).sum() > 10:
                X_train = X[mask.values]
                X_test = X[~mask.values]
                y_train = y[mask.values]
                y_test = y[~mask.values]
                split_used = f'time-based cutoff {str(cutoff.date())}'
            else:
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        else:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))
    r2 = float(r2_score(y_test, preds))

    # save
    import joblib
    joblib.dump(model, MODEL_PKL)
    with open(METRICS_JSON, 'w', encoding='utf8') as f:
        json.dump({'mae': mae, 'r2': r2, 'split_used': split_used}, f, indent=2)

    print('Split used:', split_used)
    print('MAE:', mae)
    print('R2:', r2)

if __name__ == '__main__':
    main()
