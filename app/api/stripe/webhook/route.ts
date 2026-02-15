import { NextRequest } from "next/server";
import Stripe from "stripe";
import { randomUUID } from "crypto";
import { addApiKeyForUser, findUserById, recordPayment, listKeysForUser } from "../../../../lib/db";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", { apiVersion: "2022-11-15" });

// map configured price env names to calls per minute
const ENV_PRICE_TO_CALLS: Record<string, number> = {
  TENCALLS_PRICE_ID: 10,
  TWENTYFIVECALLS_PRICE_ID: 25,
  FIFTYCALLS_PRICE_ID: 50,
  HUNDREDFIFTYCALLS_PRICE_ID: 150,
  FIVEHUNDREDCALLS_PRICE_ID: 500,
};

function getCallsFromPriceKey(keyOrId?: string) {
  if (!keyOrId) return 60;
  // if the stored value is an env var name like 'TENCALLS_PRICE_ID'
  if (typeof keyOrId === 'string' && keyOrId in ENV_PRICE_TO_CALLS) return ENV_PRICE_TO_CALLS[keyOrId as string];
  // otherwise check against actual configured price ids
  for (const envName of Object.keys(ENV_PRICE_TO_CALLS)) {
    const pid = process.env[envName];
    if (pid && pid === keyOrId) return ENV_PRICE_TO_CALLS[envName];
    // also allow partial match if someone stored the env name in the string
    if (typeof keyOrId === 'string' && keyOrId.includes(envName.replace('_PRICE_ID', ''))) return ENV_PRICE_TO_CALLS[envName];
  }
  return 60;
}

export async function POST(req: NextRequest) {
  const sig = req.headers.get('stripe-signature') || '';
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
  const body = await req.text();

  if (!webhookSecret) {
    return new Response('Webhook secret not configured', { status: 500 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, webhookSecret);
  } catch (e: any) {
    const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
    return new Response(`Webhook error: ${msg}`, { status: 400 });
  }

  // handle payment_intent.succeeded to grant key
  if (event.type === 'payment_intent.succeeded') {
    const pi = event.data.object as Stripe.PaymentIntent;
    const metadata = (pi.metadata || {}) as Record<string, string>;
    const userId = metadata.userId;
    const priceKeyName = metadata.priceKeyName || '';

    if (userId) {
      // verify amount matches price if possible
      let callsPerMin = 60;
      if (priceKeyName) {
        try {
          const priceId = process.env[priceKeyName] || priceKeyName;
          if (priceId) {
            const price = await stripe.prices.retrieve(priceId as string);
            const expected = price.unit_amount || 0;
            if ((pi.amount || 0) !== expected) {
              // amount mismatch, do not grant key
              return new Response(JSON.stringify({ received: false, reason: 'amount_mismatch' }), { status: 400 });
            }
            callsPerMin = getCallsFromPriceKey(priceKeyName) || getCallsFromPriceKey(priceId);
          }
        } catch (e) {
          // if price lookup fails, continue but log
        }
      }

      // record payment
      await recordPayment(userId || null, priceKeyName || null, (pi.amount || 0), pi.id || '');

      const user = await findUserById(userId);
      if (user) {
        // only add a paid key if the user doesn't already have one
        const existing = await listKeysForUser(user.id);
        if (!(existing || []).some((k) => k.tier === 'paid')) {
          const id = randomUUID();
            const newKey = { id, key: id, name: 'Paid key', tier: 'paid', limit: callsPerMin, createdAt: new Date().toISOString(), priceKeyName: priceKeyName || undefined };
          await addApiKeyForUser(userId, newKey);
        }
      }
    }
  }
  // handle checkout session completed (subscriptions)
  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session;
    const userId = (session.metadata || {})['userId'];
    const subscriptionId = typeof session.subscription === 'string' ? session.subscription : (session.subscription as any)?.id;
    const customerEmail = session.customer_details?.email || session.customer_email || '';

    if (subscriptionId) {
      try {
        const subscription = await stripe.subscriptions.retrieve(subscriptionId);
        const priceId = subscription.items.data[0]?.price?.id;
        let callsPerMin = 60;
        if (priceId) {
          callsPerMin = getCallsFromPriceKey(priceId);
        }

        let user = null;
        if (userId) user = await findUserById(userId);
        if (!user && customerEmail) {
          try { const { findUserByEmail } = await import('../../../../lib/db'); user = await findUserByEmail(customerEmail); } catch (e) { user = null; }
        }

        if (user) {
          // only add a paid key if the user doesn't already have one
          const existing = await listKeysForUser(user.id);
          if (!(existing || []).some((k) => k.tier === 'paid')) {
            const id = randomUUID();
            const newKey = { id, key: id, name: 'Subscription key', tier: 'paid', limit: callsPerMin, createdAt: new Date().toISOString(), priceKeyName: priceId || undefined, subscriptionId };
            await addApiKeyForUser(user.id, newKey);
            await recordPayment(user.id, priceId || null, Number(session.amount_total || 0) || 0, subscriptionId || '');
          } else {
            // still record payment but do not create a duplicate paid key
            await recordPayment(user.id, priceId || null, Number(session.amount_total || 0) || 0, subscriptionId || '');
          }
        }
      } catch (e) {
        // ignore
      }
    }
  }

  return new Response(JSON.stringify({ received: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
