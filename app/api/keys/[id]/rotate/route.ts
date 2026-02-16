import { NextRequest } from 'next/server';
import { verifyJwt } from '../../../../../lib/auth';
import { findUserById, rotateApiKeyForUser } from '../../../../../lib/db';

export async function POST(req: NextRequest, context: { params: Promise<{ id: string }> }) {
  const id = String((await context.params).id);
  const cookie = req.headers.get('cookie') || '';
  const tokenMatch = cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
  const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
  const payload = token ? verifyJwt(token) : null;
  if (!payload || !(payload as any).id) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  const userId = String((payload as any).id);
  const user = await findUserById(userId);
  if (!user) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  try {
    const newKey = await rotateApiKeyForUser(userId, id);
    // mark revealed is handled by client after display
    return new Response(JSON.stringify({ id, key: newKey }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e:any) {
    const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
    return new Response(JSON.stringify({ error: 'Rotate failed', details: msg }), { status: 500 });
  }
}
