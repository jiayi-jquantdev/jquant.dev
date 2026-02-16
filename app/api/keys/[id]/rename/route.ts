import { NextRequest } from 'next/server';
import { verifyJwt } from '../../../../lib/auth';
import { findUserById, updateApiKeyName } from '../../../../lib/db';

export async function POST(req: NextRequest, context: { params: Promise<{ id: string }> }) {
  const id = String((await context.params).id);
  const body = await req.json().catch(()=>({}));
  const name = body?.name || '';
  if (!name) return new Response(JSON.stringify({ error: 'Missing name' }), { status: 400 });

  const cookie = req.headers.get('cookie') || '';
  const tokenMatch = cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
  const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
  const payload = token ? verifyJwt(token) : null;
  if (!payload || !(payload as any).id) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  const userId = String((payload as any).id);
  const user = await findUserById(userId);
  if (!user) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  try {
    await updateApiKeyName(userId, id, name);
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e:any) {
    const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
    return new Response(JSON.stringify({ error: 'Rename failed', details: msg }), { status: 500 });
  }
}
