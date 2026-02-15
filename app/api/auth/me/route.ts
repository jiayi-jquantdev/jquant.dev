import { NextRequest } from "next/server";
import { verifyJwt } from "../../../../lib/auth";

export async function GET(req: NextRequest) {
  const cookie = req.headers.get('cookie') || '';
  const tokenMatch = cookie.split(';').map(s => s.trim()).find(s => s.startsWith('token='));
  const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
  const payload = token ? verifyJwt(token) : null;
  return new Response(JSON.stringify({ user: payload || null }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
