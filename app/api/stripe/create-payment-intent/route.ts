import { NextRequest } from "next/server";
import Stripe from "stripe";
import { verifyJwt } from "../../../../lib/auth";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", { apiVersion: "2022-11-15" });

export async function POST(req: NextRequest) {
  const body = await req.json();
  const priceKeyName = body?.priceKeyName; // e.g. 'TWENTYCALLS_PRICE_ID'
  if (!priceKeyName) return new Response(JSON.stringify({ error: 'Missing priceKeyName' }), { status: 400 });

  const priceId = process.env[priceKeyName];
  if (!priceId) return new Response(JSON.stringify({ error: 'Price not configured' }), { status: 400 });

  // try to attach user id from JWT cookie so webhook can identify who paid
  const cookie = req.headers.get('cookie') || '';
  const tokenMatch = cookie.split(';').map(s => s.trim()).find(s => s.startsWith('token='));
  const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
  const payload: any = token ? verifyJwt(token) : null;
  const userId = payload?.id || null;

  try {
    const price = await stripe.prices.retrieve(priceId);
    const amount = (price.unit_amount || 0);
    const currency = (price.currency || 'usd');

    const paymentIntent = await stripe.paymentIntents.create({
      amount,
      currency,
      metadata: { userId: userId || '' , priceKeyName },
      automatic_payment_methods: { enabled: true },
    });

    return new Response(JSON.stringify({ clientSecret: paymentIntent.client_secret }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e: any) {
    return new Response(JSON.stringify({ error: e.message || 'stripe error' }), { status: 500 });
  }
}
