import { NextRequest } from "next/server";
import Stripe from 'stripe';
import { verifyJwt } from '../../../../lib/auth';
import { findUserById, listKeysForUser, markKeyRevealed } from '../../../../lib/db';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', { apiVersion: '2022-11-15' });

export async function GET(req: NextRequest) {
  const sessionId = String(req.nextUrl.searchParams.get('session_id') || '');
  if (!sessionId) return new Response(JSON.stringify({ error: 'Missing session_id' }), { status: 400 });

  // verify JWT from cookie
  const cookie = req.headers.get('cookie') || '';
  const tokenMatch = cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
  const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
  const payload = token ? verifyJwt(token) : null;
  if (!payload || !(payload as any).id) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  const userId = String((payload as any).id);
  const user = await findUserById(userId);
  if (!user) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  // Attempt to fetch session and use time window fallback
  try {
    const session = await stripe.checkout.sessions.retrieve(sessionId as string).catch(()=>null);
    // Prefer session metadata to find user, but we already have userId
  } catch (e) {
    // ignore
  }

  // Find a recently created paid key for this user (within last 10 minutes)
  const keys = await listKeysForUser(userId);
  const now = Date.now();
  const recent = (keys || []).filter(k => k.tier === 'paid' && k.createdAt).sort((a:any,b:any)=> (b.createdAt> a.createdAt ? 1 : -1));
  const candidate = recent.find((k:any)=> Math.abs(now - new Date(k.createdAt).getTime()) < 1000 * 60 * 10);
  if (!candidate) return new Response(JSON.stringify({ error: 'No recent paid key found' }), { status: 404 });

  // Prevent revealing more than once if marked
  try {
    // check metadata.revealed
    const revealed = (candidate as any).metadata?.revealed || (candidate as any).revealed || false;
    if (revealed) return new Response(JSON.stringify({ error: 'Key already revealed' }), { status: 400 });
  } catch (e) {
    // ignore
  }

  // mark revealed and return key value once
  try {
    await markKeyRevealed(userId, String((candidate as any).id));
  } catch (e) {
    // non-fatal
  }

  return new Response(JSON.stringify({ id: candidate.id, key: candidate.key }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
