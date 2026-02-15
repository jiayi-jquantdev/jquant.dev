# Quick Start (Beginner-friendly)

This guide shows the exact commands to get the ML predictor running and test the Next.js API. Follow each step in order.

1) Install Node dependencies and start the app

```bash
# from project root
npm install
npm run dev
```

This starts the Next.js app on `http://localhost:3000`.

2) Install Python dependencies

Make sure you have Python 3.9+ installed. Then run:

```bash
pip install -r ml/requirements.txt
```

3) Get an Alpha Vantage API key

- Visit https://www.alphavantage.co/support/#api-key and sign up for a free API key (email required).
- Copy the API key string.
- Create a `.env` file in the project root with this content:

```
ALPHA_VANTAGE_API_KEY=your_key_here
ML_SERVICE_LOCAL=true
```

Replace `your_key_here` with the key you copied.

4) Collect data (this may take time due to API rate limits)

```bash
python ml/collect_data.py
python ml/calculate_returns.py
```

Note: Alpha Vantage free tier is slow — scripts wait 12 seconds between requests. For ~100 tickers this can take 20+ minutes.

5) Train the model

```bash
python ml/train_model.py
```

This creates `ml/models/stock_predictor.pkl` and `ml/models/metrics.json`.

6) Test prediction locally

```bash
python ml/test_prediction.py
```

You should see a JSON object printed with `ticker`, `predicted_return_6m`, and `confidence`.

7) Test the Next.js API endpoint

- Ensure your Next.js server is running (`npm run dev`).
- Create an API key for yourself in `data/users.json` (use existing signup UI or manually add a user with an API key in `keys` array). The header expects `Authorization: Bearer <key>`.
- Example curl:

```bash
curl -X POST http://localhost:3000/api/predict \ 
  -H "Authorization: Bearer <your_api_key>" \ 
  -H "Content-Type: application/json" \ 
  -d '{"ticker":"AAPL"}'
```

You should get a response like the sample in `ml/README.md`.

Common errors and fixes
- "ALPHA_VANTAGE_API_KEY not set": ensure `.env` exists and you restarted your shell or the Next.js server (server reads process env at start).
- "Model not trained": run `python ml/train_model.py` to generate the model, or ensure you're using `ML_SERVICE_URL` if relying on a hosted model.
- Prediction timeouts: increase the `ML_SERVICE_LOCAL` timeout in `lib/ml-predict.ts` or ensure your machine has network access to Alpha Vantage.

If you're deploying to Vercel
- Vercel serverless functions may not include Python or allow long-running processes. It's recommended to host the model and predictor on a separate service (Cloud Run, small VM, or server) and set `ML_SERVICE_URL` to that service. The Next.js endpoint will call the external ML service if `ML_SERVICE_URL` is set.
