import Link from "next/link";
import "./globals.css";
import { cookies } from "next/headers";
import { verifyJwt } from "../lib/auth";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const token = cookieStore.get('token')?.value || null;
  const payload: any = token ? verifyJwt(token) : null;
  return (
    <html lang="en">
      <body>
        <div className="h-screen flex flex-col bg-background text-foreground">
          <header className="w-full h-16 bg-foreground text-background sticky top-0 z-40">
            <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
              <div className="flex items-center gap-6">
                <Link href="/" className="font-semibold text-xl">jquant.dev</Link>
                <nav className="hidden md:flex items-center gap-4 text-sm font-medium">
                  <Link href="/docs">Docs</Link>
                </nav>
              </div>

              <nav className="flex items-center gap-3">
                {payload ? (
                  <form action="/api/auth/logout" method="post">
                    <button type="submit" className="text-sm font-medium">Logout</button>
                  </form>
                ) : (
                  <>
                    <Link href="/login" className="text-sm font-medium">Login</Link>
                    <Link href="/signup" className="text-sm font-medium">Sign up</Link>
                  </>
                )}
              </nav>
            </div>
          </header>

          <main className="flex-1 overflow-auto pb-16">
            <div className="max-w-7xl mx-auto px-4 py-8">{children}</div>
          </main>

          <footer className="fixed bottom-0 left-0 w-full h-20 footer">
            <div className="max-w-7xl mx-auto h-20 flex items-center justify-between px-4 text-sm">
              <div>
                © jquant.dev 2026 · <span className="ml-2">📷 <a href="https://instagram.com/jquant.dev" className="underline">@jquant.dev</a> · <a href="https://instagram.com/jiayi.jquant" className="underline">@jiayi.jquant</a></span>
                <div className="mt-1">Email: <a href="mailto:jiayi@jquant.dev" className="underline">jiayi@jquant.dev</a></div>
              </div>
              <div className="flex items-center gap-4">
                <a href="/terms" className="underline">Terms</a>
                <a href="/privacy" className="underline">Privacy</a>
                <a href="/legal" className="underline">Legal</a>
              </div>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
