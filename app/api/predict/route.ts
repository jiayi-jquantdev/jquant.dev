import { NextRequest } from "next/server";
import { readJson } from "../../../lib/fs-utils";
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
  const users = await readJson<any[]>('users.json');
  let foundKey: any = null;
  let tierKeyName = 'free';
  for (const u of users) {
    if (!u.keys) continue;
    const k = u.keys.find((kk: any) => kk.key === apiKey);
    if (k) {
      foundKey = k;
      // map tier
      if (k.tier === 'free') tierKeyName = 'free';
      else if (k.tier === 'paid') tierKeyName = 'paid_20'; // default paid mapping
      else tierKeyName = k.tier;
      break;
    }
  }

  if (!foundKey) return new Response(JSON.stringify({ error: 'Invalid API key' }), { status: 401 });

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
