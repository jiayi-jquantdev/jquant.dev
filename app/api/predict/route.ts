import { NextRequest } from "next/server";
import { findUserByApiKey } from "../../../lib/db";
import { checkAndIncrementKey } from "../../../lib/rate-limit";

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
  const k = found.key as any;
  let tierKeyName = 'free';
  if (k.tier === 'free') tierKeyName = 'free';
  else {
    const priceKey = k.priceKeyName || (k.metadata && k.metadata.priceKeyName) || '';
    tierKeyName = detectTierKeyFromPriceKey(priceKey as string);
  }

  const limits = TIERS[tierKeyName] || TIERS['free'];
  const rl = await checkAndIncrementKey(apiKey, limits.minute, limits.day);
  if (!rl.allowed) {
    return new Response(JSON.stringify({ error: 'Rate limit exceeded', minuteRemaining: rl.minuteRemaining, dayRemaining: rl.dayRemaining }), { status: 429 });
  }

  // For now return a dummy prediction structure; real model calls go here.
  const body = await req.json();
  const symbol = body?.symbol || 'UNKNOWN';

  return new Response(JSON.stringify({ symbol, predictions: { '1m': 0.02, '3m': 0.05, '6m': 0.12 } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
