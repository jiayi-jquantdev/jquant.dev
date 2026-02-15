import { NextRequest } from "next/server";
import Stripe from "stripe";
import { randomUUID } from "crypto";
import { addApiKeyForUser, findUserById, recordPayment } from "../../../../lib/db";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", { apiVersion: "2022-11-15" });

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
      // verify amount matches price if possible
      let callsPerMin = 60;
      if (priceKeyName && process.env[priceKeyName]) {
        try {
          const price = await stripe.prices.retrieve(process.env[priceKeyName] as string);
          const expected = price.unit_amount || 0;
          if ((pi.amount || 0) !== expected) {
            // amount mismatch, do not grant key
            return new Response(JSON.stringify({ received: false, reason: 'amount_mismatch' }), { status: 400 });
          }
          // map priceKeyName to calls per minute
          if (priceKeyName.includes('TWENTY')) callsPerMin = 20;
          else if (priceKeyName.includes('FIFTY')) callsPerMin = 50;
          else if (priceKeyName.includes('HUNDREDFIFTY')) callsPerMin = 216;
        } catch (e) {
          // if price lookup fails, continue but log
        }
      }

      // record payment
      await recordPayment(userId || null, priceKeyName || null, (pi.amount || 0), pi.id || '');

      const user = await findUserById(userId);
      if (user) {
        const id = randomUUID();
        const newKey = { id, key: id, name: 'Paid key', tier: 'paid', limit: callsPerMin, createdAt: new Date().toISOString(), priceKeyName };
        await addApiKeyForUser(userId, newKey);
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
          if (priceId.includes('TWENTY')) callsPerMin = 20;
          else if (priceId.includes('FIFTY')) callsPerMin = 50;
          else if (priceId.includes('HUNDREDFIFTY')) callsPerMin = 216;
        }

        let user = null;
        if (userId) user = await findUserById(userId);
        if (!user && customerEmail) {
          try { const { findUserByEmail } = await import('../../../../lib/db'); user = await findUserByEmail(customerEmail); } catch (e) { user = null; }
        }

        if (user) {
          const id = randomUUID();
          const newKey = { id, key: id, name: 'Subscription key', tier: 'paid', limit: callsPerMin, createdAt: new Date().toISOString(), priceKeyName: priceId || null, subscriptionId };
          await addApiKeyForUser(user.id, newKey);
          await recordPayment(user.id, priceId || null, (session.amount_total as any) || 0, subscriptionId || '');
        }
      } catch (e) {
        // ignore
      }
    }
  }

  return new Response(JSON.stringify({ received: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
