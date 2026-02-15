import Link from "next/link";
import "./globals.css";
import AuthStatusClient from "./components/AuthStatusClient";

export default async function RootLayout({ children }: { children: React.ReactNode }) {

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
                {/* client checks cookie and shows correct state */}
                <AuthStatusClient />
              </nav>
            </div>
          </header>

          <main className="flex-1 overflow-auto pb-16">
            <div className="max-w-7xl mx-auto px-4 py-8">{children}</div>
          </main>

          <footer className="fixed bottom-0 left-0 w-full h-16 footer">
            <div className="max-w-7xl mx-auto h-16 flex items-center px-4 text-sm">© jquant.dev</div>
          </footer>
        </div>
      </body>
    </html>
  );
}
