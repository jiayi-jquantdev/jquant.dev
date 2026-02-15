import { NextRequest } from "next/server";
import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", { apiVersion: "2024-11-15" });

export async function POST(req: NextRequest) {
  const body = await req.json();
  const priceIdFromBody = body?.priceId;
  const priceKeyName = body?.priceKeyName; // e.g. 'TWENTYCALLS_PRICE_ID'
  const priceId = priceIdFromBody || (priceKeyName ? process.env[priceKeyName] : undefined);
  if (!priceId) return new Response(JSON.stringify({ error: 'Missing priceId or invalid priceKeyName' }), { status: 400 });

  try {
    const origin = req.headers.get('origin') || process.env.NEXT_PUBLIC_APP_URL || '';
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      payment_method_types: ['card'],
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${origin}/dashboard?checkout=success`,
      cancel_url: `${origin}/dashboard?checkout=cancelled`,
    });
    return new Response(JSON.stringify({ url: session.url }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e: any) {
    return new Response(JSON.stringify({ error: e.message || 'stripe error' }), { status: 500 });
  }
}
