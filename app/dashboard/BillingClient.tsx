"use client";
import { useState } from "react";

export default function BillingClient() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startCheckout() {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch('/api/stripe/checkout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ priceKeyName: 'TENCALLS_PRICE_ID' }) });
      const j = await res.json();
      if (res.ok && j.url) {
        window.location.href = j.url;
      } else {
        setError(j.error || 'Failed to start checkout');
      }
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
      setError(msg || 'Network error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button onClick={startCheckout} disabled={loading} className="px-4 py-2 rounded bg-foreground text-background">
        {loading ? 'Processing…' : 'Buy more calls'}
      </button>
      {error && <div className="text-sm text-red-600">{error}</div>}
    </div>
  );
}
