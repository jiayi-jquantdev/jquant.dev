import { NextRequest } from "next/server";
import { findUserByApiKey } from "../../../lib/db";
import { checkAndIncrementKey } from "../../../lib/rate-limit";
import { predictTicker } from "../../../lib/ml-predict";
import { readJson, writeJson } from "../../../lib/fs-utils";
import fs from 'fs';
import path from 'path';

// tier limits (minute and day window)
const TIERS: Record<string, { minute: number; day: number }> = {
  free: { minute: 5, day: 25 },
  paid_10: { minute: 10, day: 10 * 720 },
  paid_25: { minute: 25, day: 25 * 720 },
  paid_50: { minute: 50, day: 50 * 720 },
  paid_150: { minute: 150, day: 150 * 720 },
  paid_500: { minute: 500, day: 500 * 720 },
};

const ENV_PRICE_TO_CALLS: Record<string, number> = {
  TENCALLS_PRICE_ID: 10,
  TWENTYFIVECALLS_PRICE_ID: 25,
  FIFTYCALLS_PRICE_ID: 50,
  HUNDREDFIFTYCALLS_PRICE_ID: 150,
  FIVEHUNDREDCALLS_PRICE_ID: 500,
};

function detectTierKeyFromPriceKey(priceKey: string) {
  if (!priceKey) return 'paid_10';
  // if priceKey is an env name
  for (const envName of Object.keys(ENV_PRICE_TO_CALLS)) {
    if (priceKey === envName) return `paid_${ENV_PRICE_TO_CALLS[envName]}`;
  }
  // if priceKey equals any configured price id
  for (const envName of Object.keys(ENV_PRICE_TO_CALLS)) {
    const pid = process.env[envName];
    if (pid && pid === priceKey) return `paid_${ENV_PRICE_TO_CALLS[envName]}`;
  }
  // fallback substring matches
  if (priceKey.toUpperCase().includes('TEN')) return 'paid_10';
  if (priceKey.toUpperCase().includes('TWENTY') || priceKey.toUpperCase().includes('TWENTYFIVE')) return 'paid_25';
  if (priceKey.toUpperCase().includes('FIFTY')) return 'paid_50';
  if (priceKey.toUpperCase().includes('HUNDRED')) return 'paid_150';
  if (priceKey.toUpperCase().includes('FIVEHUNDRED') || priceKey.toUpperCase().includes('500')) return 'paid_500';
  return 'paid_10';
}

export async function POST(req: NextRequest) {
  const apiKey = req.headers.get('x-api-key') || req.headers.get('authorization')?.replace('Bearer ', '') || null;
  if (!apiKey) return new Response(JSON.stringify({ error: 'Missing api key' }), { status: 401 });

  // find user/key
  const found = await findUserByApiKey(apiKey);
  if (!found) return new Response(JSON.stringify({ error: 'Invalid API key' }), { status: 401 });
  const k = found.key as { tier?: string; priceKeyName?: string; metadata?: { priceKeyName?: string } } | undefined;
  let tierKeyName = 'free';
  if (k?.tier === 'free') tierKeyName = 'free';
  else {
    const priceKey = k?.priceKeyName || (k?.metadata && k.metadata.priceKeyName) || '';
    tierKeyName = detectTierKeyFromPriceKey(String(priceKey));
  }

  const limits = TIERS[tierKeyName] || TIERS['free'];
  const rl = await checkAndIncrementKey(apiKey, limits.minute, limits.day);
  if (!rl.allowed) {
    return new Response(JSON.stringify({ error: 'Rate limit exceeded', minuteRemaining: rl.minuteRemaining, dayRemaining: rl.dayRemaining }), { status: 429 });
  }

  // For now return a dummy prediction structure; real model calls go here.
  const body = await req.json();
  const ticker = (body?.ticker || body?.symbol || '') as string;
  if (!ticker || typeof ticker !== 'string') return new Response(JSON.stringify({ error: 'Missing ticker' }), { status: 400 });

  // Pre-flight checks for local Python prediction
  const mlUrl = process.env.ML_SERVICE_URL;
  const mlLocal = process.env.ML_SERVICE_LOCAL === 'true';
  if (!mlUrl && mlLocal) {
    const modelPath = path.join(process.cwd(), 'ml', 'models', 'stock_predictor.pkl');
    if (!fs.existsSync(modelPath)) {
      return new Response(JSON.stringify({ error: 'Model not trained', details: 'Run ml/train_model.py to create the model first' }), { status: 400 });
    }
    if (!process.env.ALPHA_VANTAGE_API_KEY) {
      return new Response(JSON.stringify({ error: 'Server misconfiguration', details: 'ALPHA_VANTAGE_API_KEY not set on server' }), { status: 500 });
    }
  }

  try {
    const pred = await predictTicker(ticker.toUpperCase());

    // record usage in data/usage.json (increment total calls for this key)
    try {
      const usages = (await readJson<Record<string, any>>('usage.json').catch(() => ({}))) || {};
      const cur = usages[apiKey] || { calls: 0 };
      cur.calls = (cur.calls || 0) + 1;
      usages[apiKey] = cur;
      await writeJson('usage.json', usages);
    } catch (e) {
      console.log('Failed to record usage.json', e);
    }

    const out = { ...pred, timestamp: new Date().toISOString() } as unknown as Record<string, unknown>;
    return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e: any) {
    console.log('Prediction error', e?.message || e);
    const msg = String(e?.message || e || 'Unknown error');
    if (msg.toLowerCase().includes('no overview') || msg.toLowerCase().includes('invalid ticker') || msg.toLowerCase().includes('not found')) {
      return new Response(JSON.stringify({ error: 'Invalid ticker or data not found', details: msg }), { status: 400 });
    }
    if (msg.toLowerCase().includes('timed out')) {
      return new Response(JSON.stringify({ error: 'Prediction timeout', details: msg }), { status: 504 });
    }
    if (msg.toLowerCase().includes('model not trained') || msg.toLowerCase().includes('model not found')) {
      return new Response(JSON.stringify({ error: 'Model unavailable', details: msg }), { status: 400 });
    }
    return new Response(JSON.stringify({ error: 'Prediction failed', details: msg }), { status: 500 });
  }
}
