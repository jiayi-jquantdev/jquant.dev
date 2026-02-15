# ML folder

This folder contains simple Python scripts to collect fundamentals from Alpha Vantage, compute 6-month returns, train an XGBoost model, and make predictions.

Prerequisites
- Python 3.9+
- Install dependencies:

```bash
pip install -r ml/requirements.txt
```

Environment
- Set `ALPHA_VANTAGE_API_KEY` (required) — create `.env` or export in your shell.

Files
- `ml/tickers.txt` — list of tickers (one per line) to collect
- `ml/collect_data.py` — fetch fundamental `OVERVIEW` data and save `ml/data/raw_stock_data.csv` (about 12s per request)
- `ml/calculate_returns.py` — fetch daily prices and compute `return_6m`, saves `ml/data/training_data.csv`
- `ml/train_model.py` — train an XGBoost regressor on `training_data.csv`, saves `ml/models/stock_predictor.pkl`, `feature_names.json`, `metrics.json`
- `ml/predict.py` — CLI prediction: `python ml/predict.py AAPL`

Quick steps
1. Install dependencies: `pip install -r ml/requirements.txt` (1–3 minutes)
2. Set API key: `export ALPHA_VANTAGE_API_KEY=your_key_here` (instant)
3. Collect fundamentals: `python ml/collect_data.py` (for 100 tickers, ~20+ minutes due to rate limits)
4. Calculate returns: `python ml/calculate_returns.py` (similar duration)
5. Train model: `python ml/train_model.py` (couple minutes depending on data)
6. Test prediction: `python ml/predict.py AAPL` (seconds)

Notes
- Alpha Vantage enforces strict rate limits. The scripts sleep 12 seconds between calls to be conservative.
- The training pipeline in this repo is intentionally simple: features are numeric fundamentals; missing values are imputed with median; target is `return_6m` computed from price history.
- For production on Vercel, it is recommended to host the model/prediction service separately (Cloud Run, small VM, or server) and call it via `ML_SERVICE_URL`. The Next.js endpoint supports either calling a local Python subprocess or an external service.

Sample API response
When you POST to `/api/predict` with a valid API key and body `{ "ticker": "AAPL" }`, you should get a JSON response like:

```json
{
	"ticker": "AAPL",
	"predicted_return_6m": 14.2,
	"confidence": "medium",
	"timestamp": "2024-02-15T10:30:00.000Z"
}
```
