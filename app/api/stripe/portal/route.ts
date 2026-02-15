import { NextRequest } from "next/server";
import Stripe from "stripe";
import { verifyJwt } from "../../../../lib/auth";
import { findUserById } from "../../../../lib/db";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", { apiVersion: "2022-11-15" });

export async function POST(req: NextRequest) {
  const cookie = req.headers.get('cookie') || '';
  const tokenMatch = cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
  const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  const user = await findUserById(payload.id);
  if (!user) return new Response(JSON.stringify({ error: 'User not found' }), { status: 404 });

  try {
    // try to find or create a Stripe customer for this user
    const customers = await stripe.customers.list({ email: user.email, limit: 1 });
    let customer = customers.data[0];
    if (!customer) {
      customer = await stripe.customers.create({ email: user.email, metadata: { userId: user.id } });
    }

    const origin = req.headers.get('origin') || process.env.NEXT_PUBLIC_APP_URL || '';
    const session = await stripe.billingPortal.sessions.create({ customer: customer.id, return_url: `${origin}/dashboard` });
    return new Response(JSON.stringify({ url: session.url }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e: any) {
    return new Response(JSON.stringify({ error: e.message || 'stripe error' }), { status: 500 });
  }
}
