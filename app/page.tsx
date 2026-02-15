import Link from "next/link";

export default function Home() {
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

            {/* image removed per design */}
          </div>
        </section>

        <section className="max-w-6xl mx-auto px-6 py-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="panel p-6 rounded">
              <h3 className="font-semibold mb-2">API Keys</h3>
              <p className="text-sm">Create and manage keys for programmatic access.</p>
            </div>
            <div className="panel p-6 rounded">
              <h3 className="font-semibold mb-2">Predictive Models</h3>
              <p className="text-sm">Ensemble ML models tuned for short/medium horizons.</p>
            </div>
            <div className="panel p-6 rounded">
              <h3 className="font-semibold mb-2">Billing</h3>
              <p className="text-sm">Simple flat pricing with Stripe-powered checkout.</p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
