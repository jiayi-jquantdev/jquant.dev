import Link from "next/link";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      <aside className="w-64 sidebar p-4 sticky top-0">
        <div className="mb-6 font-bold">Docs</div>
        <nav className="flex flex-col gap-2 text-sm">
          <Link href="/docs/getting-started">Getting started</Link>
          <Link href="/docs/api">API Reference</Link>
          <Link href="/docs/auth">Authentication</Link>
          <Link href="/docs/pricing">Pricing</Link>
        </nav>
      </aside>

      <div className="flex-1 p-8">
        {children}
      </div>
    </div>
  );
}
