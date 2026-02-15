import { NextRequest } from "next/server";
import { verifyJwt } from "../../../../lib/auth";
import { readJson, writeJson } from "../../../../lib/fs-utils";
import { cookies } from "next/headers";
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', { apiVersion: '2022-11-15' });

export async function DELETE(req: NextRequest, context: any) {
  const id = context?.params?.id;
  // try to extract JWT from cookie or Authorization header
  const cookieHeader = req.headers.get('cookie') || '';
  let token: string | null = null;
  const m = cookieHeader.match(/(?:^|; )token=([^;]+)/);
  if (m) token = m[1];
  if (!token) {
    const auth = req.headers.get('authorization') || '';
    if (auth.startsWith('Bearer ')) token = auth.replace('Bearer ', '');
  }
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401, headers: { 'Content-Type': 'application/json' } });

  // file-based users.json handling
  const users = await readJson<any[]>('users.json');
  const user = users.find(u => u.id === payload.id);
  if (!user) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
  const keys = user.keys || [];
  const kept = [];
  let deletedKey: any = null;
  for (const k of keys) {
    if (k.id === id || k.key === id) {
      deletedKey = k;
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
        let targetPriceId = process.env[deletedKey.priceKeyName] || deletedKey.priceKeyName;
        // if targetPriceId looks like an env var name (no price_ prefix) but wasn't found, try using it directly
        if (!targetPriceId) targetPriceId = deletedKey.priceKeyName;

        // try to retrieve the price to confirm it's recurring and get its id
        let priceObj: any = null;
        try {
          if (typeof targetPriceId === 'string') {
            priceObj = await stripe.prices.retrieve(targetPriceId as string).catch(()=>null);
          }
        } catch (e) {
          priceObj = null;
        }

        // if the price is recurring (subscription), find all customers with this user's email and cancel matching subscriptions
        if (priceObj && priceObj.recurring) {
          // fetch customers by email (may be multiple)
          const customers = await stripe.customers.list({ email: user.email, limit: 10 }).catch(()=>({ data: [] } as any));
          for (const customer of (customers.data || [])) {
            const subs = await stripe.subscriptions.list({ customer: customer.id, status: 'all', limit: 100 }).catch(()=>({ data: [] } as any));
            for (const s of (subs.data || [])) {
              try {
                // check items for matching price id
                const match = (s.items.data || []).some((it: any) => {
                  if (!it.price) return false;
                  // compare price id directly
                  if (typeof targetPriceId === 'string' && it.price.id === targetPriceId) return true;
                  // compare against retrieved price id
                  if (priceObj && it.price.id === priceObj.id) return true;
                  // also accept match if price product matches (same product across plans)
                  if (priceObj && it.price.product && it.price.product === priceObj.product) return true;
                  return false;
                });
                if (match) {
                  await stripe.subscriptions.del(s.id).catch(()=>null);
                }
              } catch (e) {
                // ignore per-subscription errors
              }
            }
          }
        } else {
          // If we couldn't retrieve a recurring price, as a fallback try to cancel any subscription that references this user's email
          const customers = await stripe.customers.list({ email: user.email, limit: 10 }).catch(()=>({ data: [] } as any));
          for (const customer of (customers.data || [])) {
            const subs = await stripe.subscriptions.list({ customer: customer.id, status: 'all', limit: 100 }).catch(()=>({ data: [] } as any));
            for (const s of (subs.data || [])) {
              try { await stripe.subscriptions.del(s.id).catch(()=>null); } catch (e) {}
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
