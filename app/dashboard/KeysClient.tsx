"use client";
import { useEffect, useState } from "react";

type KeyItem = { id?: string; key?: string; name?: string; tier?: string; limit?: number; ownerId?: string };

export default function KeysClient({ initialKeys }: { initialKeys: KeyItem[] }) {
  const [keys, setKeys] = useState<KeyItem[]>(initialKeys || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

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

  function toggleMenu(id: string) {
    setOpenMenu(openMenu === id ? null : id);
  }

  async function handleDelete(keyId: string) {
    setProcessing(true);
    try {
      const res = await fetch(`/api/keys/${encodeURIComponent(keyId)}`, { method: 'DELETE' });
      if (res.ok) {
        await fetchKeys();
        setOpenMenu(null);
      } else {
        setError('Could not delete key');
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
      {loading ? <div>Loading...</div> : (
        <div>
          {keys.length === 0 && <div className="text-sm text-background">No keys found.</div>}
          <ul className="mt-4 space-y-2">
            {keys.map(k => {
              const keyId = (k as any).id || (k as any).key;
              return (
                <li key={keyId} className="p-3 border rounded flex justify-between items-center">
                  <div>
                    <div className="font-mono text-sm text-background">{keyId}</div>
                    <div className="text-xs text-background">{(k as any).name || (k as any).tier} • created</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right text-xs text-background">{k.limit || 0} calls/min</div>
                    <div className="relative">
                      <button onClick={() => toggleMenu(keyId)} className="px-2 py-1 border rounded">⋯</button>
                      {openMenu === keyId && (
                        <div className="absolute right-0 mt-2 w-40 bg-white border shadow p-2">
                          <button onClick={() => handleDelete(keyId)} className="w-full text-left px-2 py-1">Delete key</button>
                          <button onClick={() => handleUpgrade(keyId)} className="w-full text-left px-2 py-1">Upgrade key</button>
                        </div>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="mt-6 flex gap-2">
            <button onClick={createKey} className="btn btn-primary">Create paid key</button>
            <button onClick={() => purchasePrice('TWENTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 20 calls</button>
            <button onClick={() => purchasePrice('FIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 50 calls</button>
            <button onClick={() => purchasePrice('HUNDREDFIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 150 calls</button>
          </div>
          {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
        </div>
      )}

      
    </div>
  );
}
