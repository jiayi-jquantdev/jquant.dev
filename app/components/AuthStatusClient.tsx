"use client";
import { useEffect, useState } from "react";

export default function AuthStatusClient() {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    const has = document.cookie.split(';').map(s=>s.trim()).some(s=>s.startsWith('token='));
    setSignedIn(has);
  }, []);

  async function handleLogout(e: React.FormEvent) {
    e.preventDefault();
    await fetch('/api/auth/logout', { method: 'POST' });
    setSignedIn(false);
    window.location.reload();
  }

  if (signedIn) {
    return (
      <form onSubmit={handleLogout}>
        <button type="submit" className="text-sm font-medium">Logout</button>
      </form>
    );
  }

  return (
    <>
      <a href="/login" className="text-sm font-medium">Login</a>
      <a href="/signup" className="text-sm font-medium ml-3">Sign up</a>
    </>
  );
}
