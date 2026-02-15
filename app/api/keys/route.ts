import { NextRequest } from "next/server";
import { verifyJwt } from "../../../lib/auth";
import { listKeysForUser, addApiKeyForUser, findUserById } from "../../../lib/db";
import { randomUUID } from "crypto";

export async function GET(req: NextRequest) {
  const cookie = req.headers.get("cookie") || "";
  const tokenMatch = cookie.split(";").map(s=>s.trim()).find(s=>s.startsWith("token="));
  const token = tokenMatch ? tokenMatch.replace("token=", "") : null;
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });

  const user = await findUserById(payload.id);
  if (!user) return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });

  const keys = await listKeysForUser(user.id);
  return new Response(JSON.stringify({ keys: keys || [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

export async function POST(req: NextRequest) {
  // create a new key for the logged in user (this would normally be behind a paid flow)
  const cookie = req.headers.get("cookie") || "";
  const tokenMatch = cookie.split(";").map(s=>s.trim()).find(s=>s.startsWith("token="));
  const token = tokenMatch ? tokenMatch.replace("token=", "") : null;
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });

  const body = await req.json();
  const tier = body?.tier || "paid";
  const name = body?.name || (tier === 'free' ? 'Free key' : 'Paid key');

  const user = await findUserById(payload.id);
  if (!user) return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });

  // Prevent more than one paid key per account
  if (tier === 'paid') {
    const existing = await listKeysForUser(user.id);
    if ((existing || []).some(k => (k as any).tier === 'paid')) {
      return new Response(JSON.stringify({ error: 'Account already has a paid key' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
    }
  }

  const generated = randomUUID();
  const newKey = {
    id: generated,
    key: generated,
    name,
    tier,
    limit: tier === 'free' ? 5 : 60,
    createdAt: new Date().toISOString(),
  };
  await addApiKeyForUser(user.id, newKey);

  return new Response(JSON.stringify({ key: newKey }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
