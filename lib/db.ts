import { readJson, writeJson } from "./fs-utils";
import { createClient, SupabaseClient } from "@supabase/supabase-js";

// Support multiple env var names for the Supabase server secret
const SUPABASE_URL = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SECRET_KEY || process.env.supabase_secret_key || '';

let supabase: SupabaseClient | null = null;
if (SUPABASE_URL && SUPABASE_KEY) {
  supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
    // server-side only
  });
}

type Key = { id?: string; key?: string; tier?: string; priceKeyName?: string; limit?: number; createdAt?: string; metadata?: Record<string, unknown> };
type User = { id: string; email: string; password: string; created_at?: string; keys?: Key[] };

export async function findUserByEmail(email: string): Promise<User | null> {
  if (supabase) {
    const { data, error } = await supabase.from('users').select('*').eq('email', email).limit(1).maybeSingle();
    if (error) throw error;
    return (data as unknown as User) || null;
  }
  const users = await readJson<User[]>('users.json');
  return users.find(u => u.email === email) || null;
}

export async function findUserById(id: string): Promise<User | null> {
  if (supabase) {
    const { data, error } = await supabase.from('users').select('*').eq('id', id).limit(1).maybeSingle();
    if (error) throw error;
    return (data as unknown as User) || null;
  }
  const users = await readJson<User[]>('users.json');
  return users.find(u => u.id === id) || null;
}

export async function createUser(email: string, passwordHash: string): Promise<User> {
  if (supabase) {
    const { data, error } = await supabase.from('users').insert({ email, password: passwordHash }).select().single();
    if (error) throw error;
    return data as unknown as User;
  }
  const users = await readJson<User[]>('users.json');
  const id = typeof (globalThis as any)?.crypto?.randomUUID === 'function' ? (globalThis as any).crypto.randomUUID() : String(Date.now());
  const user: User = { id, email, password: passwordHash, created_at: new Date().toISOString(), keys: [] };
  users.push(user);
  await writeJson('users.json', users);
  return user;
}

export async function addApiKeyForUser(userId: string, keyObj: Key) {
  if (supabase) {
    const { error } = await supabase.from('api_keys').insert({ key: keyObj.key, user_id: userId, tier: keyObj.tier, calls_per_min: keyObj.limit || 60, metadata: keyObj }).select();
    if (error) throw error;
    return keyObj;
  }
  const users = await readJson<User[]>('users.json');
  const user = users.find(u => u.id === userId);
  if (!user) throw new Error('User not found');
  user.keys = user.keys || [];
  user.keys.push(keyObj);
  await writeJson('users.json', users);
  return keyObj;
}

export async function listKeysForUser(userId: string) {
  if (supabase) {
    const { data, error } = await supabase.from('api_keys').select('*').eq('user_id', userId);
    if (error) throw error;
    return data as unknown as Key[];
  }
  const users = await readJson<User[]>('users.json');
  const user = users.find(u => u.id === userId);
  return (user && user.keys) || [];
}

export async function removeApiKeyForUser(userId: string, keyIdentifier: string) {
  if (supabase) {
    // Use REST API with service role to avoid client-side schema assumptions
    const base = SUPABASE_URL;
    const key = SUPABASE_KEY;
    if (!base || !key) throw new Error('Supabase config missing');
    const url = `${base.replace(/\/$/, '')}/rest/v1/api_keys?user_id=eq.${encodeURIComponent(userId)}&key=eq.${encodeURIComponent(keyIdentifier)}`;
    const res = await fetch(url, { method: 'DELETE', headers: { Authorization: `Bearer ${key}` } });
    if (!res.ok) {
      const text = await res.text().catch(()=>null);
      throw new Error(String(text) || 'delete failed');
    }
    return true;
  }
  const users = await readJson<User[]>('users.json');
  const user = users.find(u => u.id === userId);
  if (!user) throw new Error('User not found');
  user.keys = (user.keys || []).filter((kk: Key) => kk.id !== keyIdentifier && kk.key !== keyIdentifier);
  await writeJson('users.json', users);
  return true;
}

export async function updateApiKeyName(userId: string, keyId: string, name: string) {
  if (supabase) {
    const base = SUPABASE_URL;
    const key = SUPABASE_KEY;
    if (!base || !key) throw new Error('Supabase config missing');
    const url = `${base.replace(/\/$/, '')}/rest/v1/api_keys?user_id=eq.${encodeURIComponent(userId)}&key=eq.${encodeURIComponent(keyId)}`;
    const res = await fetch(url, { method: 'PATCH', headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ metadata: { name } }) });
    if (!res.ok) {
      const text = await res.text().catch(()=>null);
      throw new Error(String(text) || 'update failed');
    }
    return true;
  }
  const users = await readJson<User[]>('users.json');
  const user = users.find(u => u.id === userId);
  if (!user) throw new Error('User not found');
  user.keys = user.keys || [];
  for (const k of user.keys) {
    if ((k as any).id === keyId) {
      (k as any).name = name;
      break;
    }
  }
  await writeJson('users.json', users);
  return true;
}

export async function rotateApiKeyForUser(userId: string, keyId: string) {
  const newKey = typeof (globalThis as any)?.crypto?.randomUUID === 'function' ? (globalThis as any).crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2);
  if (supabase) {
    const base = SUPABASE_URL;
    const key = SUPABASE_KEY;
    if (!base || !key) throw new Error('Supabase config missing');
    const url = `${base.replace(/\/$/, '')}/rest/v1/api_keys?user_id=eq.${encodeURIComponent(userId)}&key=eq.${encodeURIComponent(keyId)}`;
    const res = await fetch(url, { method: 'PATCH', headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ key: newKey }) });
    if (!res.ok) {
      const text = await res.text().catch(()=>null);
      throw new Error(String(text) || 'rotate failed');
    }
    return newKey;
  }
  const users = await readJson<User[]>('users.json');
  const user = users.find(u => u.id === userId);
  if (!user) throw new Error('User not found');
  user.keys = user.keys || [];
  for (const k of user.keys) {
    if ((k as any).id === keyId) {
      (k as any).key = newKey;
      break;
    }
  }
  await writeJson('users.json', users);
  return newKey;
}

export async function markKeyRevealed(userId: string, keyId: string) {
  if (supabase) {
    const base = SUPABASE_URL;
    const key = SUPABASE_KEY;
    if (!base || !key) throw new Error('Supabase config missing');
    const url = `${base.replace(/\/$/, '')}/rest/v1/api_keys?user_id=eq.${encodeURIComponent(userId)}&key=eq.${encodeURIComponent(keyId)}`;
    const res = await fetch(url, { method: 'PATCH', headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ metadata: { revealed: true } }) });
    if (!res.ok) {
      const text = await res.text().catch(()=>null);
      throw new Error(String(text) || 'mark revealed failed');
    }
    return true;
  }
  const users = await readJson<User[]>('users.json');
  const user = users.find(u => u.id === userId);
  if (!user) throw new Error('User not found');
  user.keys = user.keys || [];
  for (const k of user.keys) {
    if ((k as any).id === keyId) {
      (k as any).metadata = (k as any).metadata || {};
      (k as any).metadata.revealed = true;
      break;
    }
  }
  await writeJson('users.json', users);
  return true;
}

export async function findUserByApiKey(apiKey: string) {
  if (supabase) {
    const { data, error } = await supabase.from('api_keys').select('key, user_id, tier, created_at, metadata, users(id,email)').eq('key', apiKey).limit(1).maybeSingle();
    if (error) throw error;
    if (!data) return null;
    // fetch user
    const { data: userData } = await supabase.from('users').select('*').eq('id', data.user_id).limit(1).maybeSingle();
    return { user: userData, key: data };
  }

  const users = await readJson<User[]>('users.json');
  for (const u of users) {
    if (!u.keys) continue;
    const k = u.keys.find((kk: Key) => kk.key === apiKey);
    if (k) return { user: u, key: k };
  }
  return null;
}

export async function recordPayment(userId: string | null, priceKeyName: string | null, amount: number, stripePaymentIntent: string) {
  if (supabase) {
    const { error } = await supabase.from('payments').insert({ user_id: userId, price_key: priceKeyName, amount, stripe_payment_intent: stripePaymentIntent });
    if (error) throw error;
    return true;
  }
  // file-based fallback: append to payments.json
  const payments = (await readJson<Record<string, unknown>[]>('payments.json').catch(() => [])) as Record<string, unknown>[];
  payments.push({ id: typeof (globalThis as any)?.crypto?.randomUUID === 'function' ? (globalThis as any).crypto.randomUUID() : String(Date.now()), userId, priceKeyName, amount, stripePaymentIntent, createdAt: new Date().toISOString() });
  await writeJson('payments.json', payments);
  return true;
}
