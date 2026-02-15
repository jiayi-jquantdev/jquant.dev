import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { verifyJwt } from "../../lib/auth";
import SignupClient from "./SignupClient";

export default async function SignupPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get?.('token')?.value || null;
  const payload: any = token ? verifyJwt(token) : null;
  if (payload) redirect('/dashboard');
  return <SignupClient />;
}
