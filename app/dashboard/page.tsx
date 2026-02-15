import fs from "fs";
import path from "path";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { verifyJwt } from "../../lib/auth";
import BillingWrapper from "./BillingWrapper";

export default async function DashboardPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get?.('token')?.value || null;
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) redirect('/login');

  // load keys (simple file storage)
  const keysPath = path.join(process.cwd(), 'data', 'keys.json');
  let keys: any[] = [];
  try {
    const raw = fs.readFileSync(keysPath, 'utf-8');
    keys = JSON.parse(raw || '[]');
  } catch (e) {
    keys = [];
  }

  const userKeys = keys.filter(k => k.ownerId === payload.id);

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold">Dashboard</h2>
            <div className="text-sm text-zinc-600">Signed in as {payload?.email || payload?.id}</div>
          </div>
          <div className="flex gap-2">
            <a href="/dashboard/keys" className="px-3 py-1 border rounded">Your keys</a>
            <form action="/api/auth/logout" method="post">
              <button type="submit" className="px-3 py-1 rounded bg-foreground text-background">Log out</button>
            </form>
          </div>
        </header>

        <section className="panel p-6 rounded shadow mb-6">
          <h3 className="font-medium mb-2">API Keys</h3>
          {userKeys.length === 0 ? (
            <p className="text-zinc-600">You have no API keys yet. Create one in the keys section.</p>
          ) : (
            <ul className="space-y-3">
              {userKeys.map((k) => (
                <li key={k.id} className="p-3 border rounded flex items-center justify-between">
                  <div>
                    <div className="font-medium">{k.name || 'Key'}</div>
                    <div className="text-sm text-zinc-600">{k.id}</div>
                  </div>
                  <div className="text-sm text-zinc-500">Limit: {k.limit || 0}</div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel p-6 rounded shadow">
          <h3 className="font-medium mb-2">Billing</h3>
          <p className="text-zinc-600 mb-4">Purchase API capacity via Stripe.</p>
          <BillingWrapper />
        </section>
      </div>
    </div>
  );
}
