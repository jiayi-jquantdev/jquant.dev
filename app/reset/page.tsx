"use client";
import { useState } from 'react';

export default function ResetRequestPage() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<string | null>(null);

  async function submit(e: any) {
    e.preventDefault();
    setStatus('Sending...');
    try {
      const res = await fetch('/api/auth/reset/request', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
      if (res.ok) {
        setStatus('If that email exists, a reset link was sent.');
      } else {
        const j = await res.json().catch(()=>({}));
        setStatus(j.error || 'Error sending reset');
      }
    } catch (e: any) {
      setStatus(e.message || 'Network error');
    }
  }

  return (
    <div className="max-w-md mx-auto panel p-6 rounded">
      <h2 className="text-lg font-medium text-background mb-3">Reset your password</h2>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="block text-sm text-background mb-1">Email</label>
          <input value={email} onChange={e => setEmail(e.target.value)} className="w-full p-2 rounded border" placeholder="you@example.com" />
        </div>
        <div className="flex justify-end">
          <button className="btn" type="submit">Send reset link</button>
        </div>
        {status && <div className="text-sm text-background">{status}</div>}
      </form>
    </div>
  );
}
