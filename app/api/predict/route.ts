import { NextRequest } from "next/server";
import { findUserByApiKey } from "../../../lib/db";
import { checkAndIncrementKey } from "../../../lib/rate-limit";

// tier limits
const TIERS: Record<string, { minute: number; day: number }> = {
  free: { minute: 5, day: 25 },
  paid_20: { minute: 20, day: 14400 },
  paid_50: { minute: 50, day: 72000 },
  paid_216: { minute: 216, day: 216000 },
};

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
    if (priceKey && priceKey.includes('TWENTY')) tierKeyName = 'paid_20';
    else if (priceKey && priceKey.includes('FIFTY')) tierKeyName = 'paid_50';
    else if (priceKey && priceKey.includes('HUNDREDFIFTY')) tierKeyName = 'paid_216';
    else tierKeyName = 'paid_20';
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
