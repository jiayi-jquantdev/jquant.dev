import { readJson, writeJson } from "./fs-utils";
import { createClient, SupabaseClient } from "@supabase/supabase-js";

let supabase: SupabaseClient | null = null;
if (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY) {
  supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, {
    // server-side only
  });
}

type User = { id: string; email: string; password: string; created_at?: string; keys?: any[] };

export async function findUserByEmail(email: string): Promise<User | null> {
  if (supabase) {
    const { data, error } = await supabase.from('users').select('*').eq('email', email).limit(1).maybeSingle();
    if (error) throw error;
    return (data as any) || null;
  }
  const users = await readJson<User[]>('users.json');
  return users.find(u => u.email === email) || null;
}

export async function findUserById(id: string): Promise<User | null> {
  if (supabase) {
    const { data, error } = await supabase.from('users').select('*').eq('id', id).limit(1).maybeSingle();
    if (error) throw error;
    return (data as any) || null;
  }
  const users = await readJson<User[]>('users.json');
  return users.find(u => u.id === id) || null;
}

export async function createUser(email: string, passwordHash: string) {
  if (supabase) {
    const { data, error } = await supabase.from('users').insert({ email, password: passwordHash }).select().single();
    if (error) throw error;
    return data as any;
  }
  const users = await readJson<User[]>('users.json');
  const id = (globalThis as any).crypto?.randomUUID ? (globalThis as any).crypto.randomUUID() : String(Date.now());
  const user = { id, email, password: passwordHash, createdAt: new Date().toISOString(), keys: [] } as any;
  users.push(user);
  await writeJson('users.json', users);
  return user;
}

export async function addApiKeyForUser(userId: string, keyObj: any) {
  if (supabase) {
    const { error } = await supabase.from('api_keys').insert({ key: keyObj.key, user_id: userId, tier: keyObj.tier, calls_per_min: keyObj.callsRemainingPerMinute || 60, metadata: keyObj }).select();
    if (error) throw error;
    return keyObj;
  }
  const users = await readJson<any[]>('users.json');
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
    return data as any[];
  }
  const users = await readJson<any[]>('users.json');
  const user = users.find(u => u.id === userId);
  return (user && user.keys) || [];
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

  const users = await readJson<any[]>('users.json');
  for (const u of users) {
    if (!u.keys) continue;
    const k = u.keys.find((kk: any) => kk.key === apiKey);
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
  const payments = (await readJson<any[]>('payments.json').catch(() => [])) as any[];
  payments.push({ id: (globalThis as any).crypto?.randomUUID ? (globalThis as any).crypto.randomUUID() : String(Date.now()), userId, priceKeyName, amount, stripePaymentIntent, createdAt: new Date().toISOString() });
  await writeJson('payments.json', payments);
  return true;
}
