import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50">
      <main className="w-full max-w-3xl p-12">
        <header className="flex items-center justify-between mb-12">
          <div>
            <h1 className="text-2xl font-semibold">JQuant — Simple ML Stock Predictions</h1>
            <p className="text-sm text-zinc-600">1m / 3m / 6m return predictions via API keys</p>
          </div>
          <nav className="flex gap-4">
            <Link href="/login" className="text-sm text-foreground">Log in</Link>
            <Link href="/signup" className="text-sm text-foreground">Sign up</Link>
          </nav>
        </header>

        <section className="bg-white p-8 rounded-md shadow-sm">
          <h2 className="text-xl font-medium mb-2">Get predictive stock returns — simply</h2>
          <p className="text-zinc-600 mb-6">Start with one free API key. Buy more keys to increase call limits and get premium per-minute throughput.</p>
          <div className="flex gap-3">
            <Link href="/signup" className="px-4 py-2 rounded bg-foreground text-background">Create account</Link>
            <Link href="/dashboard" className="px-4 py-2 rounded border">Dashboard</Link>
          </div>
        </section>
      </main>
    </div>
  );
}
