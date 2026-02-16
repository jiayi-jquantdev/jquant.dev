import { NextRequest } from "next/server";
import { verifyJwt } from "../../../../lib/auth";
import { findUserByApiKey, findUserById, listKeysForUser, removeApiKeyForUser } from "../../../../lib/db";
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', { apiVersion: '2022-11-15' });

export async function DELETE(req: NextRequest, context: { params: Promise<{ id: string }> }) {
  const id = String((await context.params).id);

  // Extract cookie token in the same way as other key routes
  const cookieHeader = req.headers.get("cookie") || "";
  const tokenMatch = cookieHeader.split(";").map((s) => s.trim()).find((s) => s.startsWith("token="));
  const cookieToken = tokenMatch ? tokenMatch.replace("token=", "") : null;

  // Extract Authorization bearer token if present
  const authHeader = req.headers.get("authorization") || "";
  const authBearer = authHeader.startsWith("Bearer ") ? authHeader.replace("Bearer ", "").trim() : null;

  let actingUserId: string | null = null;
  const debug: string[] = [];

  // 1) Try cookie JWT (same approach used in app/api/keys/route.ts)
  if (cookieToken) {
    const p = verifyJwt(cookieToken as string);
    if (p && (p as any).id) {
      actingUserId = String((p as any).id);
    } else {
      debug.push("invalid_jwt_cookie");
    }
  } else {
    debug.push("no_jwt_cookie");
  }

  // 2) If still not authenticated, try Authorization Bearer as JWT
  if (!actingUserId && authBearer) {
    const p = verifyJwt(authBearer as string);
    if (p && (p as any).id) {
      actingUserId = String((p as any).id);
    } else {
      debug.push("invalid_jwt_bearer");
    }
  } else if (!authBearer) {
    debug.push("no_authorization_header");
  }

  // 3) Finally, allow Authorization bearer to be an API key
  if (!actingUserId && authBearer) {
    try {
      const found = await findUserByApiKey(authBearer);
      if (found && found.user && (found.user as any).id) {
        actingUserId = String((found.user as any).id);
      } else {
        debug.push("api_key_not_found");
      }
    } catch (e) {
      debug.push("api_key_lookup_failed");
    }
  }

  if (!actingUserId) {
    return new Response(JSON.stringify({ error: "Unauthorized", details: debug }), { status: 401, headers: { "Content-Type": "application/json" } });
  }

  // Resolve user using shared DB helper (supports Supabase or file-based)
  const user = await findUserById(actingUserId);
  if (!user) return new Response(JSON.stringify({ error: 'Unauthorized', details: ['user_not_found'] }), { status: 401 });

  // load keys via shared helper so this works with Supabase or file-based users
  const keys = (await listKeysForUser(user.id)) || [];
  let deletedKey: Record<string, unknown> | null = null;
  for (const k of keys) {
    if ((k as any).id === id || (k as any).key === id) {
      deletedKey = k as Record<string, unknown>;
      break;
    }
  }
  // Disallow deleting free-tier keys
  if (deletedKey && (deletedKey as any).tier === 'free') {
    return new Response(JSON.stringify({ error: 'Free keys cannot be deleted', details: ['free_key_cannot_be_deleted'] }), { status: 400, headers: { 'Content-Type': 'application/json' } });
  }
  // Before deleting the key, ensure there are no active Stripe subscriptions tied to it.
  if (deletedKey) {
    try {
      // 1) If the key stores a direct subscriptionId, check its status
      if (deletedKey.subscriptionId) {
        try {
          const sub = await stripe.subscriptions.retrieve(String(deletedKey.subscriptionId)).catch(()=>null);
          if (sub && (sub as any).status && (sub as any).status !== 'canceled' && (sub as any).status !== 'incomplete_expired' && (sub as any).status !== 'deleted') {
            return new Response(JSON.stringify({ error: 'Active subscription detected. Please cancel/pause your subscription in the customer center below to delete your API key. You can resubscribe anytime and gain a new key.' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
          }
        } catch (e) {
          // If we cannot retrieve subscription, be conservative and block deletion
          return new Response(JSON.stringify({ error: 'Subscription check failed', details: 'Could not verify subscription status; cancel subscription in Stripe before deleting the key' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
        }
      }

      // 2) If the key references a priceKeyName, resolve to a Stripe price id and check customers' subscriptions
      else if (deletedKey.priceKeyName) {
        const pkName = typeof deletedKey?.priceKeyName === 'string' ? deletedKey.priceKeyName : '';
        const targetPriceId = pkName ? (process.env[pkName] || pkName) : '';
        let priceObj: any = null;
        if (targetPriceId) {
          try { priceObj = await stripe.prices.retrieve(targetPriceId).catch(()=>null); } catch (e) { priceObj = null; }
        }

        // fetch customers by email and examine subscriptions
        const customers = await stripe.customers.list({ email: user.email, limit: 10 }).catch(()=>({ data: [] } as any));
        for (const customer of (customers.data || [])) {
          const subs = await stripe.subscriptions.list({ customer: (customer as any).id, status: 'all', limit: 100 }).catch(()=>({ data: [] } as any));
          for (const s of (subs.data || [])) {
            const status = (s as any).status;
            if (status === 'canceled' || status === 'incomplete_expired' || status === 'deleted') continue;
            // check items for matching price id or product
            const items = ((s as any).items?.data || []);
            const match = items.some((it: any) => {
              if (!it.price) return false;
              if (targetPriceId && it.price.id === targetPriceId) return true;
              if (priceObj && it.price.id === priceObj.id) return true;
              if (priceObj && it.price.product && it.price.product === priceObj.product) return true;
              return false;
            });
            if (match) {
              return new Response(JSON.stringify({ error: 'Active subscription detected. Please cancel/pause your subscription in the customer center below to delete your API key. You can resubscribe anytime and gain a new key.' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
            }
          }
        }
      }
      // 3) As a final conservative fallback, if any active subscription exists for this user's email, block deletion
      else {
        const customers = await stripe.customers.list({ email: user.email, limit: 10 }).catch(()=>({ data: [] } as any));
        for (const customer of (customers.data || [])) {
          const subs = await stripe.subscriptions.list({ customer: (customer as any).id, status: 'all', limit: 100 }).catch(()=>({ data: [] } as any));
          for (const s of (subs.data || [])) {
            const status = (s as any).status;
            if (status && status !== 'canceled' && status !== 'incomplete_expired' && status !== 'deleted') {
              return new Response(JSON.stringify({ error: 'Active subscription detected. Please cancel/pause your subscription in the customer center below to delete your API key. You can resubscribe anytime and gain a new key.' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
            }
          }
        }
      }
    } catch (e) {
      // On any Stripe API error, be conservative and block deletion with an explanatory message
      console.log('Stripe check error', e);
      return new Response(JSON.stringify({ error: 'Subscription check failed', details: 'Could not verify subscriptions; cancel any active subscriptions in Stripe before deleting the key' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
    }
  }

  // Safe to delete: use shared DB helper to remove the key
  try {
    await removeApiKeyForUser(user.id, id);
  } catch (e) {
    return new Response(JSON.stringify({ error: 'Delete failed', details: ['remove_failed'] }), { status: 500, headers: { 'Content-Type': 'application/json' } });
  }

  return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
