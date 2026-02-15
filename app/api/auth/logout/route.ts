import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  const cookie = `token=deleted; HttpOnly; Path=/; Max-Age=0; SameSite=Lax`;
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Set-Cookie": cookie, "Content-Type": "application/json" },
  });
}
