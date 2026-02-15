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
          <div className="max-w-6xl mx-auto px-6 py-20 flex items-center justify-between">
            <div className="max-w-2xl">
              <h1 className="text-5xl font-extrabold mb-4 text-foreground">jquant.dev</h1>
              <p className="text-lg text-foreground mb-8">Simple, reliable machine-learning stock return predictions served by an API. Get 1m / 3m / 6m horizon forecasts with API keys.</p>
              <div className="flex gap-3">
                <Link href="/signup" className="px-5 py-3 rounded bg-foreground text-background">Create account</Link>
                <Link href="/docs" className="px-5 py-3 rounded border">Documentation</Link>
              </div>
            </div>

            {/* hero illustration intentionally omitted */}
          </div>
        </section>
      </main>
    </div>
  );
}
