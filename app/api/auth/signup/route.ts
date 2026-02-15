import { NextRequest } from "next/server";
import { randomUUID } from "crypto";
import { hashPassword, createJwt } from "../../../../lib/auth";
import { createUser } from "../../../../lib/db";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { email, password } = body || {};
  if (!email || !password) {
    return new Response(JSON.stringify({ error: "Missing fields" }), { status: 400 });
  }

  const existing = await (await import('../../../../lib/db')).findUserByEmail(email);
  if (existing) return new Response(JSON.stringify({ error: 'Email exists' }), { status: 400 });

  const hashed = await hashPassword(password);
  const user = await createUser(email, hashed);
  // create initial free key
  const freeKey = typeof randomUUID === 'function' ? randomUUID() : String(Date.now());
  const keyObj = { key: freeKey, tier: 'free', callsRemainingPerMinute: 5, createdAt: new Date().toISOString() };
  await (await import('../../../../lib/db')).addApiKeyForUser(user.id, keyObj);

  const token = createJwt({ id: user.id, email: user.email });
  const cookie = `token=${token}; HttpOnly; Path=/; Max-Age=${60 * 60 * 24 * 7}; SameSite=Lax`;

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Set-Cookie": cookie, "Content-Type": "application/json" },
  });
}
