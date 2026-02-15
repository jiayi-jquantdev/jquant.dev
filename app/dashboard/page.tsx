import fs from "fs";
import path from "path";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { verifyJwt } from "../../lib/auth";
import KeysClient from "./KeysClient";
import PaymentMethodsClient from "./PaymentMethodsClient";

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
            <div className="text-sm text-background">Signed in as {payload?.email || payload?.id}</div>
          </div>
          <div className="flex gap-2">
            <form action="/api/auth/logout" method="post">
              <button type="submit" className="px-3 py-1 rounded bg-foreground text-background">Log out</button>
            </form>
          </div>
        </header>

        <section className="panel p-6 rounded shadow mb-6">
          <h3 className="font-medium mb-2">API Keys</h3>
          <KeysClient initialKeys={userKeys} />
        </section>

        <section className="panel p-6 rounded shadow">
          <h3 className="font-medium mb-2">Payment methods</h3>
          <PaymentMethodsClient />
        </section>
      </div>
    </div>
  );
}
