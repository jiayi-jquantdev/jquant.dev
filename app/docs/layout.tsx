import Link from "next/link";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      <aside className="w-64 sidebar p-4">
        <div className="mb-6 font-bold text-foreground">Docs</div>
        <nav className="flex flex-col gap-2 text-sm">
          <Link href="/docs/getting-started" className="text-foreground">Getting started</Link>
          <Link href="/docs/api" className="text-foreground">API Reference</Link>
          <Link href="/docs/auth" className="text-foreground">Authentication</Link>
          <Link href="/docs/pricing" className="text-foreground">Pricing</Link>
        </nav>
      </aside>

      <div className="flex-1 p-8">
        {children}
      </div>
    </div>
  );
}
