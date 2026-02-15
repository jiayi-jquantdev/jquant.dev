import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { verifyJwt } from "../../lib/auth";
import { listKeysForUser } from "../../lib/db";
import KeysClient from "./KeysClient";
import PaymentMethodsClient from "./PaymentMethodsClient";

export default async function DashboardPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get?.('token')?.value || null;
  const payload = token ? verifyJwt(token) : null;
  if (!payload) redirect('/login');

  const userId = String(payload.id);
  const userKeys = await listKeysForUser(userId);

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto flex flex-col items-center justify-center w-full centered-up">
        <div className="mb-6" />

        <section className="panel p-6 rounded shadow mb-6 w-full">
          <h3 className="font-medium mb-2">API Keys</h3>
          <KeysClient initialKeys={userKeys as any} />
        </section>

        <section className="panel p-6 rounded shadow w-full">
          <PaymentMethodsClient />
        </section>
      </div>
    </div>
  );
}
