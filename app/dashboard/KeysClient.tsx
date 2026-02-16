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
  const [oneTimeKeyId, setOneTimeKeyId] = useState<string | null>(null);
  const [oneTimeMode, setOneTimeMode] = useState<boolean>(false);
  const [oneTimeName, setOneTimeName] = useState<string>('');
  async function fetchKeys() {
    setLoading(true);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const tokenMatch = document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
      const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch('/api/keys', { credentials: 'include', headers });
      if (res.ok) {
        const j = await res.json();
        setKeys(j.keys || []);
      } else {
        setError('Unauthorized or error');
      }
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
      setError(msg || 'Network error');
    }
    setLoading(false);
  }

  // On mount, check for checkout session and request the one-time key
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('session_id');
    const checkout = params.get('checkout');
    if (checkout === 'success' && sessionId) {
      (async () => {
        try {
          const res = await fetch(`/api/stripe/session-result?session_id=${encodeURIComponent(sessionId)}`, { credentials: 'include' });
          if (res.ok) {
            const j = await res.json();
            if (j && j.key) {
              setRevealKey(j.key);
              setOneTimeKeyId(j.id || null);
              setOneTimeMode(true);
            }
          }
        } catch (e) {
          // ignore
        }
      })();
    }
  }, []);

  async function createKey() {
    setLoading(true);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const tokenMatch = document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
      const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch('/api/keys', { method: 'POST', credentials: 'include', headers, body: JSON.stringify({ tier: 'paid' }) });
      if (res.ok) {
        await fetchKeys();
      } else {
        setError('Could not create key');
      }
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
      setError(msg || 'Network error');
    }
    setLoading(false);
  }

  function toggleMenu(id: string) {
    setOpenMenu(openMenu === id ? null : id);
  }

  async function handleDelete(keyId: string) {
    setProcessing(true);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const tokenMatch = document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('token='));
      const token = tokenMatch ? tokenMatch.replace('token=', '') : null;
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(`/api/keys/${encodeURIComponent(keyId)}`, { method: 'DELETE', credentials: 'include', headers });
      if (res.ok) {
        await fetchKeys();
        setOpenMenu(null);
      } else {
        const j = await res.json().catch(()=>({}));
        const details = j.details && Array.isArray(j.details) ? (": " + j.details.join(", ")) : '';
        setError((j.error || 'Could not delete key') + details);
      }
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
      setError(msg || 'Network error');
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
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
      setError(msg || 'Network error');
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
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
      setError(msg || 'Network error');
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
                const keyId = k.id || k.key || '';
              return (
                <li key={keyId} className="p-3 border rounded flex justify-between items-center">
                  <div>
                      <div className="font-medium text-background">{k.name || 'API key'}</div>
                      <div className="text-xs text-background">{k.tier || ''} • created</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right text-xs text-background">{k.limit || 0} calls/min</div>
                    <div className="relative">
                      <button onClick={() => toggleMenu(keyId)} className="px-2 py-1 border rounded">⋯</button>
                      {openMenu === keyId && (
                        <div className="absolute right-0 mt-2 w-44 bg-background text-foreground border shadow p-2 key-menu">
                          <button onClick={() => handleDelete(keyId)} className="w-full text-left px-2 py-1">Delete key</button>
                          {k.tier === 'paid' && <button onClick={async () => {
                              setProcessing(true); setError(null);
                              try {
                                const res = await fetch(`/api/keys/${encodeURIComponent(keyId)}/rotate`, { method: 'POST', credentials: 'include' });
                                const j = await res.json();
                                if (res.ok && j && j.key) {
                                  setRevealKey(j.key);
                                  setOneTimeKeyId(j.id || keyId);
                                  setOneTimeMode(true);
                                } else {
                                  setError(j.error || 'Could not rotate key');
                                }
                              } catch (e:any) {
                                const msg = e && typeof e === 'object' && 'message' in e ? (e as any).message : String(e);
                                setError(msg || 'Network error');
                              }
                              setProcessing(false); setOpenMenu(null);
                            }} className="w-full text-left px-2 py-1">Change key</button>}
                          {k.tier === 'free' && <button onClick={() => { setRevealKey(k.key || k.id || null); setOpenMenu(null); }} className="w-full text-left px-2 py-1">View key</button>}
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
                <h3 className="font-medium mb-3 text-background">{oneTimeMode ? 'You can only see this key once' : 'API Key'}</h3>
                <pre className="bg-white p-3 rounded break-all">{revealKey}</pre>
                {oneTimeMode && (
                  <div className="mt-4">
                    <input value={oneTimeName} onChange={(e)=>setOneTimeName(e.target.value)} placeholder="Name this key (optional)" className="w-full p-2 border rounded mb-2" />
                    <div className="flex justify-end gap-2">
                      <button onClick={async () => {
                        if (oneTimeKeyId && oneTimeName) {
                          try {
                            const res = await fetch(`/api/keys/${encodeURIComponent(oneTimeKeyId)}/rename`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: oneTimeName }) });
                            if (res.ok) {
                              await fetchKeys();
                            }
                          } catch (e) { }
                        } else {
                          // still refresh keys
                          await fetchKeys();
                        }
                        setRevealKey(null); setOneTimeMode(false); setOneTimeKeyId(null); setOneTimeName('');
                        // remove session params from URL
                        try { const url = new URL(window.location.href); url.searchParams.delete('session_id'); url.searchParams.delete('checkout'); window.history.replaceState({}, '', url.toString()); } catch(e){}
                      }} className="px-4 py-2 border rounded">Done</button>
                    </div>
                  </div>
                )}
                {!oneTimeMode && (
                  <div className="mt-4 flex justify-end">
                    <button onClick={() => setRevealKey(null)} className="px-4 py-2 border rounded">Close</button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Only show paid-key purchase options when the user does NOT already have a paid key */}
          {!(keys || []).some(k => k.tier === 'paid') && (
            <div className="mt-6 flex items-center justify-between">
              <div className="font-medium text-background">Create paid key</div>
              <div className="flex gap-2">
                <button onClick={() => purchasePrice('TENCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 10 calls per minute</button>
                <button onClick={() => purchasePrice('TWENTYFIVECALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 25 calls per minute</button>
                <button onClick={() => purchasePrice('FIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 50 calls per minute</button>
                <button onClick={() => purchasePrice('HUNDREDFIFTYCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 150 calls per minute</button>
                <button onClick={() => purchasePrice('FIVEHUNDREDCALLS_PRICE_ID')} className="px-4 py-2 border rounded">Buy 500 calls per minute</button>
              </div>
            </div>
          )}
          {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
        </div>
      )}

      
    </div>
  );
}
