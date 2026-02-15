import { NextRequest } from "next/server";
import { verifyJwt } from "../../../lib/auth";
import { readJson, writeJson } from "../../../lib/fs-utils";
import { v4 as uuidv4 } from "uuid";

export async function GET(req: NextRequest) {
  const cookie = req.headers.get("cookie") || "";
  const tokenMatch = cookie.split(";").map(s=>s.trim()).find(s=>s.startsWith("token="));
  const token = tokenMatch ? tokenMatch.replace("token=", "") : null;
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });

  const users = await readJson<any[]>("users.json");
  const user = users.find(u => u.id === payload.id);
  if (!user) return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });

  return new Response(JSON.stringify({ keys: user.keys || [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
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

  const users = await readJson<any[]>("users.json");
  const user = users.find(u => u.id === payload.id);
  if (!user) return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });

  const newKey = {
    key: uuidv4(),
    tier,
    callsRemainingPerMinute: tier === 'free' ? 1 : 60,
    createdAt: new Date().toISOString(),
  };
  user.keys = user.keys || [];
  user.keys.push(newKey);
  await writeJson('users.json', users);

  return new Response(JSON.stringify({ key: newKey }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
