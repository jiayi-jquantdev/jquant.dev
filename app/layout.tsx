import Link from "next/link";
import "./globals.css";
import { cookies } from "next/headers";
import { verifyJwt } from "../lib/auth";
import HeaderAuthClient from "./components/HeaderAuthClient";
import MobileSidebar from "./components/MobileSidebar";

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
                <MobileSidebar />
                <Link href="/" className="sr-only sm:not-sr-only">
                  <img src="/globe.svg" alt="jquant" className="h-8 w-auto" />
                </Link>
                <div className="hidden sm:flex items-center gap-3 text-sm">
                  <span>© jquant.dev 2026 ·</span>
                  <a href="https://instagram.com/jquant.dev" target="_blank" rel="noopener noreferrer" className="underline">@jquant.dev</a>
                  <a href="https://instagram.com/jiayi.jquant" target="_blank" rel="noopener noreferrer" className="underline">@jiayi.jquant</a>
                  <a href="mailto:jiayi@jquant.dev" target="_blank" rel="noopener noreferrer" className="underline">jiayi@jquant.dev</a>
                  <Link href="/terms" target="_blank" rel="noopener noreferrer" className="underline">Terms</Link>
                  <Link href="/privacy" target="_blank" rel="noopener noreferrer" className="underline">Privacy</Link>
                  <Link href="/legal" target="_blank" rel="noopener noreferrer" className="underline">Legal</Link>
                </div>
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

          {/* footer removed — links moved to header */}
        </div>
      </body>
    </html>
  );
}
