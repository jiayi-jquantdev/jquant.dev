#!/usr/bin/env python3
"""
Clean training data, engineer features, normalize, and retrain model.
Writes cleaned features, retrains XGBRegressor, saves model and metrics.
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
MODEL_PKL = MODELS_DIR / 'stock_predictor_cleaned.pkl'
FEATURES_CSV = MODELS_DIR / 'cleaned_features.csv'
METRICS_JSON = MODELS_DIR / 'metrics_cleaned.json'

def to_num(s):
    try:
        return float(s)
    except Exception:
        return np.nan

def main():
    df = pd.read_csv(TRAIN_CSV)

    # normalize column names
    df.columns = [c.strip() for c in df.columns]

    # Convert numeric-like columns
    for col in df.columns:
        df[col] = df[col].replace(['', 'None', '-', 'NA'], np.nan)
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # filter extreme outliers in target
    df = df[df['return_6m'].notna()]
    df = df[(df['return_6m'] >= -50.0) & (df['return_6m'] <= 100.0)].copy()

    # Define ratio columns to winsorize
    ratio_cols = [
        'PriceToBookRatio', 'PriceToSalesRatioTTM', 'EVToEBITDA', 'EVToRevenue',
        'PERatio', 'PEGRatio', 'ProfitMargin', 'ReturnOnEquityTTM', 'ReturnOnAssetsTTM',
        'PriceToSalesRatioTTM'
    ]

    present_ratio_cols = [c for c in ratio_cols if c in df.columns]

    # cap (winsorize) at 99th percentile
    for c in present_ratio_cols:
        p99 = df[c].quantile(0.99)
        df[c] = np.where(df[c] > p99, p99, df[c])

    # Drop rows missing key columns
    for key in ['PERatio', 'ReturnOnEquityTTM', 'return_6m']:
        if key in df.columns:
            df = df[df[key].notna()]
            df = df[df[key] != 0]

    # Feature engineering: create composite scores and momentum
    # value_score: lower P/E, P/B, P/S -> higher score
    def inv_norm(series):
        s = series.copy().astype(float)
        s = (s - s.min()) / (s.max() - s.min()) if s.max() != s.min() else s*0
        return 1 - s

    features = pd.DataFrame(index=df.index)

    # Basic numeric features
    for col in ['MarketCapitalization', 'latest_close', 'RevenueTTM', 'GrossProfitTTM']:
        if col in df.columns:
            features[col] = df[col].fillna(0)

    # value components
    comps = []
    for col in ['PERatio', 'PriceToBookRatio', 'PriceToSalesRatioTTM']:
        if col in df.columns:
            comps.append(inv_norm(df[col].fillna(df[col].median())))
    if comps:
        features['value_score'] = pd.concat(comps, axis=1).mean(axis=1)

    # growth momentum
    growth_cols = [c for c in ['QuarterlyRevenueGrowthYOY', 'QuarterlyEarningsGrowthYOY'] if c in df.columns]
    if growth_cols:
        features['growth_momentum'] = df[growth_cols].fillna(0).mean(axis=1)

    # momentum from moving averages
    if 'latest_close' in df.columns and '50DayMovingAverage' in df.columns:
        features['mom_50'] = df['latest_close'] / (df['50DayMovingAverage'].replace(0, np.nan))
    if 'latest_close' in df.columns and '200DayMovingAverage' in df.columns:
        features['mom_200'] = df['latest_close'] / (df['200DayMovingAverage'].replace(0, np.nan))

    # profitability composite
    prof_cols = [c for c in ['ProfitMargin', 'ReturnOnAssetsTTM', 'ReturnOnEquityTTM'] if c in df.columns]
    if prof_cols:
        features['profitability'] = df[prof_cols].fillna(0).mean(axis=1)

    # leverage size
    if 'SharesOutstanding' in df.columns:
        features['log_shares_out'] = np.log1p(df['SharesOutstanding'].fillna(0))

    # add existing numeric columns up to reach many features
    extra = ['ForwardPE', 'EVToRevenue', 'EVToEBITDA', 'BookValue', 'Beta']
    for c in extra:
        if c in df.columns:
            features[c] = df[c].fillna(df[c].median())

    # fill remaining NaNs
    features = features.fillna(0)

    # Normalize features to 0-1 range
    from sklearn.preprocessing import MinMaxScaler
    scaler = MinMaxScaler()
    X = scaler.fit_transform(features.values)
    X_df = pd.DataFrame(X, index=features.index, columns=features.columns)

    y = df['return_6m'].astype(float)

    # Save cleaned features
    cleaned = pd.concat([df[['Symbol']].reset_index(drop=True), X_df.reset_index(drop=True), y.reset_index(drop=True)], axis=1)
    cleaned.to_csv(FEATURES_CSV, index=False)

    # Train/test split and train model
    X_train, X_test, y_train, y_test = train_test_split(X_df, y, test_size=0.2, random_state=42)
    model = XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.05, random_state=42)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))
    r2 = float(r2_score(y_test, preds))

    # save model and metrics
    import joblib
    joblib.dump(model, MODEL_PKL)
    with open(METRICS_JSON, 'w', encoding='utf8') as f:
        json.dump({'mae': mae, 'r2': r2}, f, indent=2)

    print('Saved cleaned features to', FEATURES_CSV)
    print('MAE:', mae)
    print('R2:', r2)

if __name__ == '__main__':
    main()
