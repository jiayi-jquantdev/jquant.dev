import { NextRequest } from "next/server";
import { verifyJwt } from "../../../../lib/auth";
import { readJson, writeJson } from "../../../../lib/fs-utils";
import { findUserByApiKey } from "../../../../lib/db";
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', { apiVersion: '2022-11-15' });

export async function DELETE(req: NextRequest, context: { params: Promise<{ id: string }> }) {
  const id = String((await context.params).id);
  // try to extract JWT from cookie or Authorization header
  const cookieHeader = req.headers.get('cookie') || '';
  let token: string | null = null;
  const m = cookieHeader.match(/(?:^|; )token=([^;]+)/);
  if (m) token = m[1];
  if (!token) {
    const auth = req.headers.get('authorization') || '';
    if (auth.startsWith('Bearer ')) token = auth.replace('Bearer ', '');
  }
  let payload = token ? verifyJwt(token) : null;
  let actingUserId: string | null = null;
  if (payload && (payload as any).id) {
    actingUserId = String((payload as any).id);
  }

  // If no JWT payload, allow fallback to API key in Authorization header
  if (!actingUserId) {
    const authHeader = req.headers.get('authorization') || '';
    if (authHeader.startsWith('Bearer ')) {
      const possibleKey = authHeader.replace('Bearer ', '').trim();
      try {
        const found = await findUserByApiKey(possibleKey);
        if (found && found.user && (found.user as any).id) {
          actingUserId = String((found.user as any).id);
        }
      } catch (e) {
        // ignore and fall through to unauthorized
      }
    }
  }

  if (!actingUserId) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401, headers: { 'Content-Type': 'application/json' } });

  // file-based users.json handling
  const users = await readJson<{ id: string; email: string; keys?: any[] }[]>('users.json');
  const user = users.find(u => u.id === actingUserId);
  if (!user) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
  const keys = user.keys || [];
  const kept: unknown[] = [];
  let deletedKey: Record<string, unknown> | null = null;
  for (const k of keys) {
    if ((k as any).id === id || (k as any).key === id) {
      deletedKey = k as Record<string, unknown>;
    } else {
      kept.push(k);
    }
  }
  user.keys = kept;
  await writeJson('users.json', users);

  // if deleted key maps to a subscription price, try to cancel subscriptions for this user
  try {
    if (deletedKey) {
      // 1) If we have a subscriptionId saved on the key, cancel that subscription directly
      if (deletedKey.subscriptionId) {
        try {
          await stripe.subscriptions.del(String(deletedKey.subscriptionId));
        } catch (e) {
          // ignore
        }
      } else if (deletedKey.priceKeyName) {
        // 2) Resolve the stored priceKeyName to an actual Stripe price id if an env var was stored
        const pkName = typeof deletedKey?.priceKeyName === 'string' ? deletedKey.priceKeyName : '';
        let targetPriceId = pkName ? (process.env[pkName] || pkName) : '';

        // try to retrieve the price to confirm it's recurring and get its id
        let priceObj: unknown = null;
        try {
          if (typeof targetPriceId === 'string' && targetPriceId) {
            priceObj = await stripe.prices.retrieve(targetPriceId as string).catch(()=>null);
          }
        } catch (e) {
          priceObj = null;
        }

        // if the price is recurring (subscription), find all customers with this user's email and cancel matching subscriptions
        if (priceObj && (priceObj as any).recurring) {
          // fetch customers by email (may be multiple)
          const customers = await stripe.customers.list({ email: user.email, limit: 10 }).catch(()=>({ data: [] } as unknown as { data: unknown[] }));
          for (const customer of (customers.data || [])) {
            const subs = await stripe.subscriptions.list({ customer: (customer as any).id, status: 'all', limit: 100 }).catch(()=>({ data: [] } as unknown as { data: unknown[] }));
            for (const s of (subs.data || [])) {
              try {
                // check items for matching price id
                const match = ((s as any).items?.data || []).some((it: any) => {
                  if (!it.price) return false;
                  if (typeof targetPriceId === 'string' && (it.price as any).id === targetPriceId) return true;
                  if (priceObj && (it.price as any).id === (priceObj as any).id) return true;
                  if (priceObj && (it.price as any).product && (it.price as any).product === (priceObj as any).product) return true;
                  return false;
                });
                if (match) {
                  await stripe.subscriptions.del(((s as unknown) as Stripe.Subscription).id).catch(()=>null);
                }
              } catch (e) {
                // ignore per-subscription errors
              }
            }
          }
        } else {
          // If we couldn't retrieve a recurring price, as a fallback try to cancel any subscription that references this user's email
          const customers = await stripe.customers.list({ email: user.email, limit: 10 }).catch(()=>({ data: [] } as unknown as { data: unknown[] }));
          for (const customer of (customers.data || [])) {
            const subs = await stripe.subscriptions.list({ customer: (customer as any).id, status: 'all', limit: 100 }).catch(()=>({ data: [] } as unknown as { data: unknown[] }));
            for (const s of (subs.data || [])) {
              try { await stripe.subscriptions.del((s as any).id).catch(()=>null); } catch (e) {}
            }
          }
        }
      }
    }
  } catch (e) {
    // ignore stripe errors but log server-side if desired
  }

  return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
