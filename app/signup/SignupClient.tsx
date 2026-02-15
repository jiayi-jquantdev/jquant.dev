"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function SignupClient() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await fetch('/api/auth/signup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
    if (res.ok) {
      try { const bc = new BroadcastChannel('auth'); bc.postMessage('login'); bc.close(); } catch {}
      router.push('/dashboard');
    } else {
      const j = await res.json();
      setError(j.error || 'Signup failed');
    }
  }

  return (
    <div className="h-full flex items-center justify-center p-8 overflow-hidden">
      <form onSubmit={submit} className="w-full max-w-md bg-background p-8 rounded shadow overflow-hidden">
        <h2 className="text-xl font-medium mb-4">Create account</h2>
        {error && <div className="text-sm text-red-600 mb-2">{error}</div>}
        <label className="block mb-2">
          <div className="text-sm">Email</div>
          <input className="w-full border p-2 rounded" value={email} onChange={e=>setEmail(e.target.value)} />
        </label>
        <label className="block mb-4">
          <div className="text-sm">Password</div>
          <input type="password" className="w-full border p-2 rounded" value={password} onChange={e=>setPassword(e.target.value)} />
        </label>
        <div className="flex gap-2">
          <button type="submit" className="btn btn-primary">Sign up</button>
        </div>
      </form>
    </div>
  );
}
