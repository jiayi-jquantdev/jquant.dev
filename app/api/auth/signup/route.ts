import { NextRequest } from "next/server";
import { v4 as uuidv4 } from "uuid";
import { hashPassword, createJwt } from "../../../../lib/auth";
import { readJson, writeJson } from "../../../../lib/fs-utils";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { email, password } = body || {};
  if (!email || !password) {
    return new Response(JSON.stringify({ error: "Missing fields" }), { status: 400 });
  }

  const users = await readJson<any[]>("users.json");
  if (users.find((u) => u.email === email)) {
    return new Response(JSON.stringify({ error: "Email exists" }), { status: 400 });
  }

  const hashed = await hashPassword(password);
  const id = uuidv4();
  const freeKey = uuidv4();
  const user = {
    id,
    email,
    password: hashed,
    createdAt: new Date().toISOString(),
    keys: [
      {
        key: freeKey,
        tier: "free",
        callsRemainingPerMinute: 1,
        createdAt: new Date().toISOString(),
      },
    ],
  };
  users.push(user);
  await writeJson("users.json", users);

  const token = createJwt({ id: user.id, email: user.email });
  const cookie = `token=${token}; HttpOnly; Path=/; Max-Age=${60 * 60 * 24 * 7}; SameSite=Lax`;

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Set-Cookie": cookie, "Content-Type": "application/json" },
  });
}
