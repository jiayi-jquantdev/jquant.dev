"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function HeaderAuthClient({ initialUser }: { initialUser?: any }) {
  const [user, setUser] = useState<any>(initialUser || null);
  const [loading, setLoading] = useState<boolean>(!initialUser);
  const router = useRouter();

  useEffect(() => {
    let mounted = true;
    async function check() {
      try {
        const res = await fetch('/api/auth/me', { credentials: 'include' });
        if (res.ok) {
          const j = await res.json();
          if (mounted) setUser(j.user || null);
        } else {
          if (mounted) setUser(null);
        }
      } catch (e) {
        if (mounted) setUser(null);
      }
      if (mounted) setLoading(false);
    }
    check();
    const bc = typeof window !== 'undefined' ? new BroadcastChannel('auth') : null;
    if (bc) bc.onmessage = () => { if (mounted) check(); };
    return () => { mounted = false; if (bc) bc.close(); };
  }, []);

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    setUser(null);
    router.push('/');
  }

  return (
    <nav className="flex items-center gap-3">
      {loading ? (
        <span className="text-sm text-background">Loading...</span>
      ) : user ? (
        <button onClick={logout} className="text-sm font-medium">Logout</button>
      ) : (
        <>
          <Link href="/login" className="text-sm font-medium">Login</Link>
          <Link href="/signup" className="text-sm font-medium">Sign up</Link>
        </>
      )}
    </nav>
  );
}
