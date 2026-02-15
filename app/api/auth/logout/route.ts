import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  const cookie = `token=deleted; HttpOnly; Path=/; Max-Age=0; SameSite=Lax`;
  return new Response(null, {
    status: 303,
    headers: { "Set-Cookie": cookie, Location: "/" },
  });
}
