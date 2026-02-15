#!/usr/bin/env python3
"""
Predict 6-month return for a given ticker using trained model.
CLI usage: python ml/predict.py AAPL
Outputs JSON to stdout.
"""
import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
import joblib
import numpy as np
import pandas as pd

load_dotenv()

API_KEY = os.getenv('alphavantage_api_key')
ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / 'models'
MODEL_PKL = MODELS_DIR / 'stock_predictor.pkl'
FEATURES_JSON = MODELS_DIR / 'feature_names.json'
METRICS_JSON = MODELS_DIR / 'metrics.json'

BASE_URL = 'https://www.alphavantage.co/query'

def fetch_overview(symbol: str):
    params = {'function': 'OVERVIEW', 'symbol': symbol, 'apikey': API_KEY}
    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data or 'Symbol' not in data:
        raise ValueError('No overview data for ' + symbol)
    return data

def load_model():
    if not MODEL_PKL.exists():
        raise FileNotFoundError('Model not found; run ml/train_model.py')
    model = joblib.load(MODEL_PKL)
    with open(FEATURES_JSON, 'r', encoding='utf8') as f:
        features = json.load(f)
    metrics = {}
    if METRICS_JSON.exists():
        with open(METRICS_JSON, 'r', encoding='utf8') as f:
            metrics = json.load(f)
    return model, features, metrics

def build_feature_vector(overview, features):
    row = {}
    for f in features:
        # try several keys
        val = overview.get(f) or overview.get(f.upper()) or overview.get(f.lower())
        try:
            row[f] = float(val)
        except Exception:
            row[f] = np.nan
    df = pd.DataFrame([row])
    df = df.fillna(df.median(numeric_only=True))
    return df

def confidence_from_metrics(metrics, pred):
    mae = metrics.get('mae') or 0.0
    if mae == 0:
        return 'medium'
    # heuristic: larger prediction relative to MAE -> higher confidence
    if abs(pred) > mae * 2:
        return 'high'
    if abs(pred) > mae * 0.5:
        return 'medium'
    return 'low'

def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'ticker required'}))
        sys.exit(1)
    ticker = sys.argv[1].upper()
    if API_KEY is None:
        print(json.dumps({'error': 'alphavantage_api_key not set'}))
        sys.exit(1)

    model, features, metrics = load_model()
    overview = fetch_overview(ticker)
    X = build_feature_vector(overview, features)
    pred = model.predict(X)[0]
    conf = confidence_from_metrics(metrics, pred)
    out = {'ticker': ticker, 'predicted_return_6m': float(round(float(pred), 4)), 'confidence': conf}
    print(json.dumps(out))

if __name__ == '__main__':
    main()
