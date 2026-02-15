import { NextRequest } from "next/server";
import { readJson } from "../../../../lib/fs-utils";
import { comparePassword, createJwt } from "../../../../lib/auth";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { email, password } = body || {};
  if (!email || !password) {
    return new Response(JSON.stringify({ error: "Missing fields" }), { status: 400 });
  }

  const users = await readJson<any[]>("users.json");
  const user = users.find((u) => u.email === email);
  if (!user) return new Response(JSON.stringify({ error: "Invalid" }), { status: 401 });

  const ok = await comparePassword(password, user.password);
  if (!ok) return new Response(JSON.stringify({ error: "Invalid" }), { status: 401 });

  const token = createJwt({ id: user.id, email: user.email });
  const cookie = `token=${token}; HttpOnly; Path=/; Max-Age=${60 * 60 * 24 * 7}; SameSite=Lax`;
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Set-Cookie": cookie, "Content-Type": "application/json" },
  });
}
