import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { verifyJwt } from "../lib/auth";

export default async function Home() {
  const cookieStore = await cookies();
  const token = cookieStore.get?.('token')?.value || null;
  const payload: any = token ? verifyJwt(token) : null;
  if (payload) redirect('/dashboard');

  return (
    <div className="min-h-screen flex items-center justify-center">
      <main className="w-full">
        <section className="min-h-[72vh] flex items-center">
          <div className="max-w-4xl mx-auto px-6 py-16 text-center" style={{ transform: 'translateY(-1.5rem)' }}>
            <h1 className="text-5xl md:text-6xl font-extrabold mb-6 leading-tight text-foreground">jquant.dev</h1>
            <ul className="list-disc list-inside text-lg md:text-xl text-foreground mb-8 space-y-3 leading-relaxed">
              <li>Simple, reliable machine-learning stock return predictions served by an API.</li>
              <li>Get 1m / 3m / 6m horizon forecasts.</li>
              <li>Subscription-backed API keys with per-minute rate limits.</li>
            </ul>
            <div className="flex justify-center gap-3">
              <Link href="/signup" className="px-5 py-3 rounded bg-foreground text-background">Create account</Link>
              <Link href="/docs" className="px-5 py-3 rounded border">Documentation</Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
