import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { verifyJwt } from "../../lib/auth";
import LoginClient from "./LoginClient";

export default async function LoginPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get?.('token')?.value || null;
  const payload = token ? verifyJwt(token) : null;
  if (payload) redirect('/dashboard');
  return <LoginClient />;
}
