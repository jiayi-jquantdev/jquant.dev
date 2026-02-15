import { NextRequest } from 'next/server';
import { findUserByApiKey } from '../../../../lib/db';

export async function POST(req: NextRequest) {
  const apiKey = req.headers.get('x-api-key') || req.headers.get('authorization')?.replace('Bearer ', '') || null;
  if (!apiKey) return new Response(JSON.stringify({ error: 'Missing api key' }), { status: 401 });

  const found = await findUserByApiKey(apiKey);
  if (!found) return new Response(JSON.stringify({ error: 'Invalid API key' }), { status: 401 });
  const user = found.user as any;
  if (!user || !user.admin) return new Response(JSON.stringify({ error: 'Admin required' }), { status: 403 });

  // If ML service URL is configured, proxy the retrain command
  const mlUrl = process.env.ML_SERVICE_URL;
  if (mlUrl) {
    try {
      const res = await fetch(`${mlUrl.replace(/\/$/, '')}/admin/train`, { method: 'POST' });
      const json = await res.json();
      return new Response(JSON.stringify({ ok: true, remote: true, result: json }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    } catch (e) {
      console.log('Failed to call remote ML service', e);
      return new Response(JSON.stringify({ error: 'Remote retrain failed', details: String(e) }), { status: 500 });
    }
  }

  // Otherwise, trigger local training as a background process
  try {
    const { spawn } = await import('child_process');
    const script = 'ml/train_model.py';
    const proc = spawn('python3', [script], { detached: true, stdio: 'ignore' });
    proc.unref();
    console.log('Started background training process');
    return new Response(JSON.stringify({ ok: true, message: 'Training started' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e) {
    console.log('Failed to spawn training process', e);
    return new Response(JSON.stringify({ error: 'Failed to start training', details: String(e) }), { status: 500 });
  }
}
