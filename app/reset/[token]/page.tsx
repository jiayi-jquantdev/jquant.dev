"use client";
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function ResetSubmitPage({ params }: { params: { token: string } }) {
  // In Next app router, params come in server props; but we accept via props too
  const token = (params && params.token) || (typeof window !== 'undefined' ? window.location.pathname.split('/').pop() : '');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const router = useRouter();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus('Resetting...');
    try {
      const res = await fetch('/api/auth/reset/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, password }) });
      if (res.ok) {
        setStatus('Password reset. You can now log in.');
        setTimeout(() => router.push('/login'), 1200);
      } else {
        const j = await res.json().catch(()=>({}));
        setStatus(j.error || 'Error resetting password');
      }
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
      setStatus(msg || 'Network error');
    }
  }

  return (
    <div className="max-w-md mx-auto panel p-6 rounded">
      <h2 className="text-lg font-medium text-background mb-3">Choose a new password</h2>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="block text-sm text-background mb-1">New password</label>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} className="w-full p-2 rounded border" />
        </div>
        <div className="flex justify-end">
          <button className="btn" type="submit">Set password</button>
        </div>
        {status && <div className="text-sm text-background">{status}</div>}
      </form>
    </div>
  );
}
