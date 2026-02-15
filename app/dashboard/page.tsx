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
      <div className="max-w-4xl mx-auto flex flex-col items-center justify-center w-full centered-up">
        <div className="mb-6" />

        <section className="panel p-6 rounded shadow mb-6 w-full">
          <h3 className="font-medium mb-2">API Keys</h3>
          <KeysClient initialKeys={userKeys} />
        </section>

        <section className="panel p-6 rounded shadow w-full">
          <PaymentMethodsClient />
        </section>
      </div>
    </div>
  );
}
