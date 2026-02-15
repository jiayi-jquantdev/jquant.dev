import { NextResponse } from 'next/server';
import { readJson, writeJson } from '../../../../../lib/fs-utils';
import { hashPassword } from '../../../../../lib/auth';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const token = body.token;
    const password = body.password;
    if (!token || !password) return NextResponse.json({ error: 'Missing token or password' }, { status: 400 });

    const users = await readJson<Record<string, any>[]>('users.json').catch(() => []);
    const user = users.find(u => u.resetToken === token && u.resetExpires && (u.resetExpires as number) > Date.now());
    if (!user) return NextResponse.json({ error: 'Invalid or expired token' }, { status: 400 });

    const hashed = await hashPassword(password);
    user.password = hashed;
    delete user.resetToken;
    delete user.resetExpires;
    await writeJson('users.json', users);

    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
    return NextResponse.json({ error: msg || String(e) }, { status: 500 });
  }
}

export const runtime = 'nodejs';
