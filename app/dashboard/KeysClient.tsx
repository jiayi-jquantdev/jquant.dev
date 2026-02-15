"use client";
import { useEffect, useState } from "react";

type KeyItem = { id?: string; key?: string; name?: string; tier?: string; limit?: number; ownerId?: string };

export default function KeysClient({ initialKeys }: { initialKeys: KeyItem[] }) {
  const [keys, setKeys] = useState<KeyItem[]>(initialKeys || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [revealKey, setRevealKey] = useState<string | null>(null);

  useEffect(() => { fetchKeys(); }, []);

  async function fetchKeys() {
    setLoading(true);
    try {
      const res = await fetch('/api/keys', { credentials: 'include' });
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
      const res = await fetch('/api/keys', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tier: 'paid' }) });
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

  function toggleMenu(id: string) {
    setOpenMenu(openMenu === id ? null : id);
  }

  async function handleDelete(keyId: string) {
    setProcessing(true);
    try {
      const res = await fetch(`/api/keys/${encodeURIComponent(keyId)}`, { method: 'DELETE', credentials: 'include' });
      if (res.ok) {
        await fetchKeys();
        setOpenMenu(null);
      } else {
        const j = await res.json().catch(()=>({}));
        setError(j.error || 'Could not delete key');
      }
    } catch (e: any) {
      setError(e.message || 'Network error');
    }
    setProcessing(false);
  }

  async function handleUpgrade(keyId: string) {
    setProcessing(true); setError(null);
    try {
      // redirect to checkout for an upgrade price
      const res = await fetch('/api/stripe/checkout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ priceKeyName: 'TWENTYCALLS_PRICE_ID' }) });
      const j = await res.json();
      if (res.ok && j.url) {
        window.location.href = j.url;
      } else {
        setError(j.error || 'Failed to create checkout');
      }
    } catch (e: any) {
      setError(e.message || 'Network error');
    }
    setProcessing(false);
  }

  async function purchasePrice(priceKeyName: string) {
    setProcessing(true); setError(null);
    try {
      const res = await fetch('/api/stripe/checkout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ priceKeyName }) });
      const j = await res.json();
      if (res.ok && j.url) {
        window.location.href = j.url;
      } else {
        setError(j.error || 'Failed to create checkout');
      }
    } catch (e: any) {
      setError(e.message || 'Network error');
    }
    setProcessing(false);
  }

  return (
    <div>
      {loading ? (
        <div className="space-y-2">
          <div className="p-3 border rounded animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-3 bg-gray-200 rounded w-1/4"></div>
          </div>
          <div className="p-3 border rounded animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-3 bg-gray-200 rounded w-1/4"></div>
          </div>
          <div className="p-3 border rounded animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-3 bg-gray-200 rounded w-1/4"></div>
          </div>
        </div>
      ) : (
        <div>
          {keys.length === 0 && <div className="text-sm text-background">No keys found.</div>}
          <ul className="mt-4 space-y-2">
            {keys.map(k => {
              const keyId = (k as any).id || (k as any).key;
              return (
                <li key={keyId} className="p-3 border rounded flex justify-between items-center">
                  <div>
                    <div className="font-medium text-background">{(k as any).name || 'API key'}</div>
                    <div className="text-xs text-background">{(k as any).tier || ''} • created</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right text-xs text-background">{k.limit || 0} calls/min</div>
                    <div className="relative">
                      <button onClick={() => toggleMenu(keyId)} className="px-2 py-1 border rounded">⋯</button>
                      {openMenu === keyId && (
                        <div className="absolute right-0 mt-2 w-44 bg-background text-foreground border shadow p-2 key-menu">
                          <button onClick={() => handleDelete(keyId)} className="w-full text-left px-2 py-1">Delete key</button>
                          {(k as any).tier === 'free' && <button onClick={() => { setRevealKey((k as any).key || (k as any).id); setOpenMenu(null); }} className="w-full text-left px-2 py-1">View key</button>}
                        </div>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          {/* Reveal modal for free key */}
          {revealKey && (
            <div className="fixed inset-0 flex items-center justify-center bg-black/40">
              <div className="panel p-6 rounded shadow max-w-md w-full">
                <h3 className="font-medium mb-3 text-background">API Key</h3>
                <pre className="bg-white p-3 rounded break-all">{revealKey}</pre>
                <div className="mt-4 flex justify-end">
                  <button onClick={() => setRevealKey(null)} className="px-4 py-2 border rounded">Close</button>
                </div>
              </div>
            </div>
          )}

          {/* Only show paid-key purchase options when the user does NOT already have a paid key */}
          {!(keys || []).some(k => (k as any).tier === 'paid') && (
            <div className="mt-6 flex items-center justify-between">
              <div className="font-medium text-background">Create paid key</div>
              <div className="flex gap-2">
                <button onClick={() => purchasePrice('TWENTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 20 calls per minute</button>
                <button onClick={() => purchasePrice('FIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 50 calls per minute</button>
                <button onClick={() => purchasePrice('HUNDREDFIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 150 calls per minute</button>
                <button onClick={() => purchasePrice('SIXHUNDREDCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 600 calls per minute</button>
              </div>
            </div>
          )}
          {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
        </div>
      )}

      
    </div>
  );
}
