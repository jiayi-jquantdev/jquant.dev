import { NextResponse } from 'next/server';
import { readJson, writeJson } from '../../../../../lib/fs-utils';
import crypto from 'crypto';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const email = (body.email || '').toLowerCase();
    if (!email) return NextResponse.json({ error: 'Missing email' }, { status: 400 });

    // find user in file-based store
    const users = await readJson<any[]>('users.json').catch(() => []);
    const user = users.find(u => u.email && u.email.toLowerCase() === email);
    if (!user) {
      // Don't reveal whether email exists — return ok
      return NextResponse.json({ ok: true });
    }

    const token = crypto.randomUUID ? crypto.randomUUID() : crypto.randomBytes(16).toString('hex');
    const expires = Date.now() + 1000 * 60 * 60; // 1 hour
    user.resetToken = token;
    user.resetExpires = expires;
    await writeJson('users.json', users);

    const resetUrl = `${process.env.NEXT_PUBLIC_BASE_URL || 'https://jquant.dev'}/reset/${token}`;

    const resendKey = process.env.RESEND_API_KEY;
    if (resendKey) {
      await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${resendKey}` },
        body: JSON.stringify({
          from: 'no-reply@jquant.dev',
          to: email,
          subject: 'Reset your jquant.dev password',
          html: `<p>Click the link below to reset your password. This link expires in 1 hour.</p><p><a href="${resetUrl}">${resetUrl}</a></p>`
        })
      });
    }

    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: e.message || String(e) }, { status: 500 });
  }
}

export const runtime = 'nodejs';
