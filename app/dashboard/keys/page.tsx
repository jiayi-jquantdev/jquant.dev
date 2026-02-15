"use client";
import { useEffect, useState, useRef } from "react";
import { loadStripe } from "@stripe/stripe-js";

type KeyItem = { key: string; tier: string; createdAt: string; callsRemainingPerMinute?: number };

export default function KeysPage() {
  const [keys, setKeys] = useState<KeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchKeys(); }, []);

  async function fetchKeys() {
    setLoading(true);
    const res = await fetch('/api/keys');
    if (res.ok) {
      const j = await res.json();
      setKeys(j.keys || []);
    } else {
      setError('Unauthorized or error');
    }
    setLoading(false);
  }

  async function createKey() {
    const res = await fetch('/api/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tier: 'paid' }) });
    if (res.ok) {
      await fetchKeys();
    } else {
      setError('Could not create key');
    }
  }

  const [showPayment, setShowPayment] = useState(false);
  const [paymentPriceKey, setPaymentPriceKey] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const stripeRef = useRef<any>(null);
  const elementsRef = useRef<any>(null);

  async function openPayment(priceKeyName: string) {
    setPaymentPriceKey(priceKeyName);
    setShowPayment(true);
    setTimeout(initStripe, 50);
  }

  async function initStripe() {
    if (!paymentPriceKey) return;
    if (!cardRef.current) return;
    if (!stripeRef.current) {
      stripeRef.current = await loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY || '');
    }
    if (!elementsRef.current) {
      const elements = stripeRef.current!.elements();
      const card = elements.create('card');
      card.mount(cardRef.current);
      elementsRef.current = { elements, card };
    }
  }

  async function submitPayment() {
    if (!paymentPriceKey) return setError('No price selected');
    setProcessing(true);
    try {
      const res = await fetch('/api/stripe/create-payment-intent', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ priceKeyName: paymentPriceKey }) });
      if (!res.ok) throw new Error('Could not create payment intent');
      const j = await res.json();
      const clientSecret = j.clientSecret;
      const stripe = stripeRef.current;
      const { error } = await stripe.confirmCardPayment(clientSecret, { payment_method: { card: elementsRef.current.card } });
      if (error) {
        setError(error.message || 'Payment failed');
        setProcessing(false);
        return;
      }

      // simple flow: after successful payment, create paid key for user
      const k = await fetch('/api/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tier: 'paid' }) });
      if (k.ok) {
        await fetchKeys();
        setShowPayment(false);
      } else {
        setError('Payment succeeded but could not create key');
      }
    } catch (e: any) {
      setError(e.message || 'Payment error');
    }
    setProcessing(false);
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-3xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-medium">Your API keys</h2>
        </header>
        <section className="panel p-6 rounded shadow">
          {loading ? <div>Loading...</div> : (
            <div>
              {keys.length === 0 && <div className="text-sm text-zinc-600">No keys found.</div>}
              <ul className="mt-4 space-y-2">
                {keys.map(k => (
                  <li key={k.key} className="p-3 border rounded flex justify-between">
                    <div>
                      <div className="font-mono text-sm">{k.key}</div>
                      <div className="text-xs text-zinc-500">{k.tier} • created {new Date(k.createdAt).toLocaleString()}</div>
                    </div>
                    <div className="text-right text-xs">{k.callsRemainingPerMinute} calls/min</div>
                  </li>
                ))}
              </ul>

              <div className="mt-6 flex gap-2">
                <button onClick={createKey} className="px-4 py-2 bg-foreground text-background rounded">Create paid key</button>
                <button onClick={() => openPayment('TWENTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 20 calls</button>
                <button onClick={() => openPayment('FIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 50 calls</button>
                <button onClick={() => openPayment('HUNDREDFIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 150 calls</button>
              </div>
              {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
            </div>
          )}
        </section>
        {showPayment && (
          <div className="fixed inset-0 flex items-center justify-center bg-black/40">
            <div className="panel p-6 rounded shadow max-w-md w-full">
              <h3 className="font-medium mb-3">Enter card details</h3>
              <div ref={cardRef} className="mb-4" />
              <div className="flex gap-2">
                <button onClick={submitPayment} className="px-4 py-2 bg-foreground text-background rounded" disabled={processing}>{processing ? 'Processing...' : 'Pay'}</button>
                <button onClick={() => setShowPayment(false)} className="px-4 py-2 border rounded">Cancel</button>
              </div>
              {error && <div className="text-sm text-red-600 mt-2">{error}</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
