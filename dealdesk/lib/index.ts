import { gunzipSync } from "zlib";
import { createDecipheriv } from "crypto";

const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/web";
const TTL_MS = 15 * 60 * 1000;

export type Tender = {
  id: string; c: string; rg: string; s: string; g: string; t: string; b: string; v: number | null; dl: string;
  dd: number | null; d: string; ev: number | null; sc: number | null; src: string; st: string; l: string; n: number;
  acc: string; rt: string; ig?: number | null; if?: string;
};
export type Supplier = {
  q?: number; n: string; c?: string; rg?: string; tr?: string; s?: string; s2?: string; ty?: string; td?: string;
  epc?: string; lg?: string; p?: string; cm?: string; x?: string; w?: number; u?: number; bc?: string; web?: string; lw?: string; why?: string;
};

const mem: Record<string, { at: number; data: unknown }> = {};

async function load<T>(name: string, decode: (b: Buffer) => T): Promise<T> {
  const hit = mem[name];
  if (hit && Date.now() - hit.at < TTL_MS) return hit.data as T;
  const r = await fetch(`${RAW}/${name}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  const data = decode(Buffer.from(await r.arrayBuffer()));
  mem[name] = { at: Date.now(), data };
  return data;
}

// A tender whose deadline has passed is closed and never shown (the data files are refreshed every few hours,
// so the check runs against today's date at request time). Tenders without a stated deadline stay.
export function isClosed(deadline: string | undefined): boolean {
  const d = Date.parse(String(deadline || "").slice(0, 10));
  if (!isFinite(d)) return false;
  const now = new Date();
  return d < Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
}

export async function tenders(): Promise<Tender[]> {
  try {
    const all: Tender[] = await load("tenders.json.gz", (b) => JSON.parse(gunzipSync(b).toString("utf-8")));
    return all.filter((r) => !isClosed(r.dl));
  } catch {
    return [];
  }
}

export async function suppliers(): Promise<{ rows: Supplier[]; error?: string }> {
  const key = process.env.WEB_INDEX_KEY;
  if (!key) return { rows: [], error: "WEB_INDEX_KEY is not configured" };
  try {
    const rows = await load("suppliers.enc", (b) => {
      const nonce = b.subarray(0, 12), tag = b.subarray(b.length - 16), body = b.subarray(12, b.length - 16);
      const d = createDecipheriv("aes-256-gcm", Buffer.from(key, "base64"), nonce);
      d.setAuthTag(tag);
      const plain = Buffer.concat([d.update(body), d.final()]);
      return JSON.parse(gunzipSync(plain).toString("utf-8")) as Supplier[];
    });
    return { rows };
  } catch (e) {
    return { rows: [], error: String(e).includes("404") ? "The supplier index is being built - try again in a few minutes" : String(e).slice(0, 120) };
  }
}

export function facet<T>(rows: T[], get: (r: T) => string | undefined, limit = 300): [string, number][] {
  const m = new Map<string, number>();
  for (const r of rows) {
    const v = get(r);
    if (v) m.set(v, (m.get(v) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit);
}

export const words = (q: string) => q.toLowerCase().split(/[\s,]+/).map((w) => w.trim()).filter((w) => w.length > 1);
