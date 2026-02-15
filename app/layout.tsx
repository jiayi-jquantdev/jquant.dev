import Link from "next/link";
import "./globals.css";
import { cookies } from "next/headers";
import { verifyJwt } from "../lib/auth";
import HeaderAuthClient from "./components/HeaderAuthClient";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const token = cookieStore.get('token')?.value || null;
  const payload: any = token ? verifyJwt(token) : null;
  return (
    <html lang="en">
      <body>
        <div className="flex flex-col bg-background text-foreground">
          <header className="w-full h-16 bg-foreground text-background sticky top-0 z-40">
            <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
              <div className="flex items-center gap-6">
                <Link href="/" className="font-semibold text-xl">jquant.dev</Link>
              </div>

              <div className="flex items-center gap-4">
                <Link href="/docs" className="hidden md:inline text-sm font-medium">Docs</Link>
                <HeaderAuthClient initialUser={payload} />
              </div>
            </div>
          </header>

          <main className="main-content flex-1 pb-16">
            <div className="max-w-7xl mx-auto px-4 py-8">{children}</div>
          </main>

          <footer className="w-full h-20 footer">
            <div className="max-w-7xl mx-auto h-20 flex items-center justify-between px-4 text-sm">
              <div className="flex items-center gap-4">
                <span>© jquant.dev 2026 ·</span>
                <span className="flex items-center gap-2">
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="inline-block">
                    <rect x="3" y="3" width="18" height="18" rx="5" ry="5"></rect>
                    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
                    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
                  </svg>
                  <a href="https://instagram.com/jquant.dev" className="underline">@jquant.dev</a>
                  <span>·</span>
                  <a href="https://instagram.com/jiayi.jquant" className="underline">@jiayi.jquant</a>
                </span>
              </div>

              <div className="flex items-center gap-4">
                <a href="mailto:jiayi@jquant.dev" target="_blank" rel="noopener noreferrer" className="underline">jiayi@jquant.dev</a>
                <Link href="/terms" target="_blank" rel="noopener noreferrer" className="underline">Terms</Link>
                <Link href="/privacy" target="_blank" rel="noopener noreferrer" className="underline">Privacy</Link>
                <Link href="/legal" target="_blank" rel="noopener noreferrer" className="underline">Legal</Link>
              </div>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
