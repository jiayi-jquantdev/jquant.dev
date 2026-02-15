import { NextRequest } from "next/server";
import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", { apiVersion: "2022-11-15" });

export async function POST(req: NextRequest) {
  const body = await req.json();
  const mode = body?.mode || 'payment';
  const priceIdFromBody = body?.priceId;
  const priceKeyName = body?.priceKeyName; // e.g. 'TWENTYCALLS_PRICE_ID'
  const priceId = priceIdFromBody || (priceKeyName ? process.env[priceKeyName] : undefined);
  if (mode === 'payment' && !priceId) return new Response(JSON.stringify({ error: 'Missing priceId or invalid priceKeyName' }), { status: 400 });

  try {
    const origin = req.headers.get('origin') || process.env.NEXT_PUBLIC_APP_URL || '';
    // If a priceId is provided, detect whether it's recurring (subscription)
    if (priceId) {
      const price = await stripe.prices.retrieve(priceId);
      const isRecurring = !!(price.recurring);
      const chosenMode = mode === 'setup' ? 'setup' : (isRecurring ? 'subscription' : 'payment');
      const session = await stripe.checkout.sessions.create({
        mode: chosenMode as any,
        payment_method_types: ['card'],
        line_items: chosenMode === 'setup' ? undefined : [{ price: priceId, quantity: 1 }],
        success_url: chosenMode === 'setup' ? `${origin}/dashboard?setup=success` : `${origin}/dashboard?checkout=success`,
        cancel_url: chosenMode === 'setup' ? `${origin}/dashboard?setup=cancelled` : `${origin}/dashboard?checkout=cancelled`,
      });
      return new Response(JSON.stringify({ url: session.url }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    } else {
      // no priceId (setup mode likely)
      const setupSession = await stripe.checkout.sessions.create({
        mode: 'setup',
        payment_method_types: ['card'],
        success_url: `${origin}/dashboard?setup=success`,
        cancel_url: `${origin}/dashboard?setup=cancelled`,
      });
      return new Response(JSON.stringify({ url: setupSession.url }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
  } catch (e: any) {
    return new Response(JSON.stringify({ error: e.message || 'stripe error' }), { status: 500 });
  }
}
