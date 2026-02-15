"use client";
import { useState } from "react";

export default function PaymentMethodsClient() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function addPaymentMethod() {
    setLoading(true); setError(null);
    try {
      const res = await fetch('/api/stripe/portal', { method: 'POST' });
      const j = await res.json();
      if (res.ok && j.url) {
        window.location.href = j.url;
      } else {
        setError(j.error || 'Could not open customer portal');
      }
    } catch (e: any) {
      setError(e.message || 'Network error');
    }
    setLoading(false);
  }

  return (
    <div>
      <p className="text-background mb-3">Manage your payment methods via Stripe.</p>
      <div className="flex gap-3">
        <button onClick={addPaymentMethod} disabled={loading} className="btn btn-primary">Add payment method</button>
      </div>
      {error && <div className="text-sm text-red-600 mt-2">{error}</div>}
    </div>
  );
}
