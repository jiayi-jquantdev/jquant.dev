import { NextRequest } from "next/server";
import { verifyJwt } from "../../../../lib/auth";
import { readJson, writeJson } from "../../../../lib/fs-utils";

export async function DELETE(req: NextRequest, context: any) {
  const id = context?.params?.id;
  const cookie = req.headers.get("cookie") || "";
  const tokenMatch = cookie.split(";").map(s=>s.trim()).find(s=>s.startsWith("token="));
  const token = tokenMatch ? tokenMatch.replace("token=", "") : null;
  const payload: any = token ? verifyJwt(token) : null;
  if (!payload) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });

  // file-based users.json handling
  const users = await readJson<any[]>('users.json');
  const user = users.find(u => u.id === payload.id);
  if (!user) return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
  user.keys = (user.keys || []).filter((k: any) => !(k.id === id || k.key === id));
  await writeJson('users.json', users);

  return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
