import Link from "next/link";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen bg-background text-foreground">
          <header className="w-full bg-foreground text-background sticky top-0 z-40">
            <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
              <div className="flex items-center gap-6">
                <Link href="/" className="font-semibold text-xl">jquant.dev</Link>
                <nav className="hidden md:flex items-center gap-4 text-sm font-medium">
                  <Link href="/docs">Docs</Link>
                </nav>
              </div>

              <nav className="flex items-center gap-3">
                <Link href="/login" className="text-sm font-medium">Login</Link>
                <Link href="/signup" className="text-sm font-medium">Sign up</Link>
              </nav>
            </div>
          </header>

          <main className="max-w-7xl mx-auto px-4 py-8">{children}</main>

          <footer className="w-full mt-24 border-t py-8">
            <div className="max-w-7xl mx-auto px-4 text-sm text-center">© jquant.dev</div>
          </footer>
        </div>
      </body>
    </html>
  );
}
