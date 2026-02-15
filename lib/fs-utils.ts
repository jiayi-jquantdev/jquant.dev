import { promises as fs } from "fs";
import path from "path";

const dataDir = path.join(process.cwd(), "data");

export async function readJson<T = unknown>(filename: string): Promise<T> {
  const p = path.join(dataDir, filename);
  try {
    const raw = await fs.readFile(p, "utf8");
    return JSON.parse(raw) as T;
  } catch (e) {
    return [] as unknown as T;
  }
}

export async function writeJson(filename: string, obj: unknown) {
  const p = path.join(dataDir, filename);
  await fs.writeFile(p, JSON.stringify(obj, null, 2), "utf8");
}
