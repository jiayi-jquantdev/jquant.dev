import { NextRequest } from "next/server";
import { verifyJwt } from "../../../../lib/auth";
import { readJson, writeJson } from "../../../../lib/fs-utils";
import { cookies } from "next/headers";
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', { apiVersion: '2022-11-15' });

export async function DELETE(req: NextRequest, context: any) {
  const id = context?.params?.id;
  const cookie = req.headers.get('cookie') || '';
  const tokenMatch = cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
  const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

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
      if (deletedKey.subscriptionId) {
        await stripe.subscriptions.del(deletedKey.subscriptionId as string).catch(()=>null);
      } else if (deletedKey.priceKeyName) {
        const price = await stripe.prices.retrieve(deletedKey.priceKeyName as string).catch(()=>null);
        if (price && (price as any).recurring) {
          const customers = await stripe.customers.list({ email: user.email, limit: 1 });
          const customer = customers.data[0];
          if (customer) {
            const subs = await stripe.subscriptions.list({ customer: customer.id, status: 'all', limit: 100 });
            for (const s of subs.data) {
              for (const item of s.items.data) {
                if (item.price && item.price.id === (price as any).id) {
                  await stripe.subscriptions.del(s.id);
                }
              }
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
