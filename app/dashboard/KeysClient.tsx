"use client";
import { useEffect, useState, useRef } from "react";
import { loadStripe } from "@stripe/stripe-js";

type KeyItem = { id: string; name?: string; tier?: string; limit?: number; ownerId?: string };

export default function KeysClient({ initialKeys }: { initialKeys: KeyItem[] }) {
  const [keys, setKeys] = useState<KeyItem[]>(initialKeys || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchKeys(); }, []);

  async function fetchKeys() {
    setLoading(true);
    try {
      const res = await fetch('/api/keys');
      if (res.ok) {
        const j = await res.json();
        setKeys(j.keys || []);
      } else {
        setError('Unauthorized or error');
      }
    } catch (e: any) {
      setError(e.message || 'Network error');
    }
    setLoading(false);
  }

  async function createKey() {
    setLoading(true);
    try {
      const res = await fetch('/api/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tier: 'paid' }) });
      if (res.ok) {
        await fetchKeys();
      } else {
        setError('Could not create key');
      }
    } catch (e: any) {
      setError(e.message || 'Network error');
    }
    setLoading(false);
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
    <div>
      {loading ? <div>Loading...</div> : (
        <div>
          {keys.length === 0 && <div className="text-sm text-background">No keys found.</div>}
          <ul className="mt-4 space-y-2">
            {keys.map(k => (
              <li key={k.id} className="p-3 border rounded flex justify-between">
                <div>
                  <div className="font-mono text-sm text-background">{k.id}</div>
                  <div className="text-xs text-background">{k.name || k.tier} • created</div>
                </div>
                <div className="text-right text-xs text-background">{k.limit || 0} calls/min</div>
              </li>
            ))}
          </ul>

          <div className="mt-6 flex gap-2">
            <button onClick={createKey} className="btn btn-primary">Create paid key</button>
            <button onClick={() => openPayment('TWENTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 20 calls</button>
            <button onClick={() => openPayment('FIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 50 calls</button>
            <button onClick={() => openPayment('HUNDREDFIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 150 calls</button>
          </div>
          {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
        </div>
      )}

      {showPayment && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40">
          <div className="panel p-6 rounded shadow max-w-md w-full">
            <h3 className="font-medium mb-3 text-background">Enter card details</h3>
            <div ref={cardRef} className="mb-4" />
            <div className="flex gap-2">
              <button onClick={submitPayment} className="btn btn-primary" disabled={processing}>{processing ? 'Processing...' : 'Pay'}</button>
              <button onClick={() => setShowPayment(false)} className="px-4 py-2 border rounded">Cancel</button>
            </div>
            {error && <div className="text-sm text-red-600 mt-2">{error}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
