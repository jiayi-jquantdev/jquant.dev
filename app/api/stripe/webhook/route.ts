import { NextRequest } from "next/server";
import Stripe from "stripe";
import { randomUUID } from "crypto";
import { readJson, writeJson } from "../../../../lib/fs-utils";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", { apiVersion: "2024-11-15" });

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
    return new Response(`Webhook error: ${e.message}`, { status: 400 });
  }

  // handle payment_intent.succeeded to grant key
  if (event.type === 'payment_intent.succeeded') {
    const pi = event.data.object as Stripe.PaymentIntent;
    const metadata = (pi.metadata || {}) as Record<string, string>;
    const userId = metadata.userId;
    const priceKeyName = metadata.priceKeyName || '';

    if (userId) {
      // create a paid key for the user
      // verify amount matches price if possible
      if (priceKeyName && process.env[priceKeyName]) {
        try {
          const price = await stripe.prices.retrieve(process.env[priceKeyName] as string);
          const expected = price.unit_amount || 0;
          if ((pi.amount || 0) !== expected) {
            // amount mismatch, do not grant key
            return new Response(JSON.stringify({ received: false, reason: 'amount_mismatch' }), { status: 400 });
          }
        } catch (e) {
          // if price lookup fails, continue but log
        }
      }

      const users = await readJson<any[]>('users.json');
      const user = users.find(u => u.id === userId);
      if (user) {
        const newKey = { key: randomUUID(), tier: 'paid', callsRemainingPerMinute: 60, createdAt: new Date().toISOString(), priceKeyName };
        user.keys = user.keys || [];
        user.keys.push(newKey);
        await writeJson('users.json', users);
      }
    }
  }

  return new Response(JSON.stringify({ received: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
