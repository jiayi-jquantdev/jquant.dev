import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "jquant.dev",
  description: "jquant.dev — simple ML stock return predictions via API",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <div className="min-h-screen flex flex-col">
          <header className="w-full border-b">
            <div className="max-w-6xl mx-auto flex items-center justify-between p-4">
              <a href="/" className="text-lg font-bold text-foreground">jquant.dev</a>
              <nav className="flex gap-4 items-center">
                <a href="/" className="text-sm text-foreground">Home</a>
                <a href="/docs" className="text-sm text-foreground">Docs</a>
                <a href="/dashboard" className="text-sm text-foreground">Dashboard</a>
                <a href="/login" className="text-sm text-foreground">Log in</a>
                <a href="/signup" className="text-sm text-foreground">Sign up</a>
              </nav>
            </div>
          </header>

          <main className="flex-1">{children}</main>

          <footer className="w-full border-t">
            <div className="max-w-6xl mx-auto p-4 text-sm text-zinc-600">© {new Date().getFullYear()} jquant.dev</div>
          </footer>
        </div>
      </body>
    </html>
  );
}
