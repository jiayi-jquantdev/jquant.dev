"use client";
import { useRouter } from "next/navigation";

export default function DashboardPage() {
  const router = useRouter();

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/');
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-3xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-medium">Dashboard</h2>
          <div className="flex gap-2">
            <a href="/dashboard/keys" className="px-3 py-1 border rounded">Your keys</a>
            <button onClick={logout} className="px-3 py-1 rounded bg-foreground text-background">Log out</button>
          </div>
        </header>

        <section className="bg-white p-6 rounded shadow">
          <p className="text-zinc-600">Welcome — manage your API keys and billing from here.</p>
        </section>
      </div>
    </div>
  );
}
