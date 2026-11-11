import { normalizeSuppliers } from "@/lib/supfit";
import { gunzipSync } from "zlib";
import { createDecipheriv } from "crypto";

const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/web";
const TTL_MS = 15 * 60 * 1000;

export type Tender = {
  id: string; c: string; rg: string; s: string; g: string; t: string; b: string; v: number | null; dl: string;
  dd: number | null; d: string; ev: number | null; sc: number | null; src: string; st: string; l: string; n: number;
  acc: string; rt: string; ig?: number | null; if?: string; fw?: string; ff?: string;
};
export type Supplier = {
  q?: number; n: string; c?: string; rg?: string; tr?: string; s?: string; s2?: string; ty?: string; td?: string;
  epc?: string; lg?: string; p?: string; cm?: string; x?: string; w?: number; u?: number; bc?: string; web?: string; lw?: string; why?: string;
  sh?: number; hs?: string; sp?: string; in?: string; wt?: string; hd?: string;
  rc?: number; wb?: string;  // refined layer (leads/refine.py): an open conflict; the basis of the official website
  ct?: string;  // contact printed by an official directory (person; phone; e-mail)
  em?: string; nt?: string;  // size signals from the universe: employees (Wikidata), notable company
  ds?: string; du?: string;  // origin exporters from a trade directory (leads/origin_exporters.py): the directory and the listing
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
  const raw = String(deadline || "").trim();
  const d = /^\d{4}-\d{2}-\d{2}/.test(raw) ? Date.parse(raw.slice(0, 10)) : Date.parse(raw);  // ISO, or the sheet's "04 Dec 2026"
  if (isFinite(d) && d < Date.UTC(1990, 0, 1)) return false;  // a mis-parse is never "closed"
  if (!isFinite(d)) return false;
  const now = new Date();
  return d < Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
}

// The compact view the profile matcher and the country page use, built from the server's one tender store (the same
// strings, no second copy of 128k notices).
let compact: { at: number; rows: Tender[] } | null = null;
export async function tenders(): Promise<Tender[]> {
  try {
    const { allTenders } = await import("@/lib/panel");
    const store = await allTenders();
    if (compact && compact.rows.length && Date.now() - compact.at < 900_000) return compact.rows;
    const f = (v: string) => { const n = parseFloat(String(v || "").replace(/,/g, "")); return Number.isFinite(n) ? n : null; };
    const INTL = /^international|world bank|\(icb\)|\bicb\b|^global tender/i;
    const rows: Tender[] = store.rows.map((r) => {
      const acc = (r.access || "").toLowerCase();
      return { id: r.id, c: r.country, rg: r.region, s: r.sector, g: r.commodity || "", t: r.title_en, b: r.buyer, v: f(r.est_value_usd), dl: r.deadline,
        dd: f(r.days_left), d: r.decision, ev: f(r.ev_usd), sc: f(r.fit || r.score), src: r.source, st: r.stage, l: r.link, n: r.new ? 1 : 0,
        acc: acc.includes("set-aside") ? "set-aside" : INTL.test(acc) ? "intl" : "", rt: r.route, fw: r.fit_why, ff: r.fit_flags };
    });
    compact = { at: Date.now(), rows };
    return rows;
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
    return { rows: normalizeSuppliers(rows) };
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

// Fresh contract winners read as sales leads (leads/winners.py): who won, where, what they now have to buy.
export type Winner = { d: string; w: string[]; wc: string; c: string; b: string; t: string; v: number; k: "commodity" | "contractor"; n: string[]; cm: string; s: string; l: string; id: string; sc: number; e?: string; ws?: string; ce?: string[]; cp?: string[]; cs?: string; wd?: string };
export async function winners(): Promise<{ at: string; rows: Winner[]; error?: string }> {
  const key = process.env.WEB_INDEX_KEY;
  if (!key) return { at: "", rows: [], error: "WEB_INDEX_KEY is not configured" };
  try {
    return await load("winners.enc", (b) => {
      const nonce = b.subarray(0, 12), tag = b.subarray(b.length - 16), body = b.subarray(12, b.length - 16);
      const d = createDecipheriv("aes-256-gcm", Buffer.from(key, "base64"), nonce);
      d.setAuthTag(tag);
      return JSON.parse(gunzipSync(Buffer.concat([d.update(body), d.final()])).toString("utf-8")) as { at: string; rows: Winner[] };
    });
  } catch (e) {
    return { at: "", rows: [], error: String(e).slice(0, 120) };
  }
}
/** Winners filtered by free words (winner, country ISO3, need, title) and kind, best first. */
export async function findWinners(q: { text?: string; kind?: string; country?: string; n?: number; size?: string }) {
  const all = await winners();
  const words = (q.text || "").toLowerCase().split(/\s+/).filter((w) => w.length > 1);
  const rows = all.rows.filter((r) => {
    if (q.kind && r.k !== q.kind) return false;
    // contract size: small < USD 1M, mid 1-50M, large > 50M (contracts without a stated value pass)
    if (q.size && r.v && (q.size === "small" ? r.v >= 1e6 : q.size === "mid" ? r.v < 1e6 || r.v > 50e6 : r.v <= 50e6)) return false;
    if (q.country && r.c !== q.country.toUpperCase() && !r.wc.includes(q.country.toUpperCase())) return false;
    if (!words.length) return true;
    const hay = `${r.w.join(" ")} ${r.t} ${r.n.join(" ")} ${r.cm} ${r.b} ${r.c} ${r.wc}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
  return { at: all.at, total: rows.length, rows: rows.slice(0, q.n || 20), error: all.error };
}

// Company and buyer footprints from public award records (leads/footprints.py).
export type Footprint = { sz?: "small" | "mid" | "large"; n: string; a: number; u: number; y: Record<string, number>; c: Record<string, number>; b: string[]; wc: string; l: { d: string; t: string; u: string; c: string }[] };
export type BuyerProfile = { n: string; c: string; a: number; u: number; y: Record<string, number>; s: { n: string; a: number; sh: number | null }[]; t3: number | null };
type Shard = { at: string; companies: Record<string, Footprint>; buyers: Record<string, BuyerProfile> };
type Names = { at: string; c: [string, number, string][]; b: [string, number][] };
const FP_STOP = new Set(["co", "ltd", "limited", "llc", "inc", "plc", "sa", "sas", "srl", "spa", "gmbh", "ag", "bv", "pvt", "private", "the", "and", "of", "corp",
  "corporation", "company", "sdn", "bhd", "pte", "jsc", "ojsc", "pjsc", "cjsc", "pty", "sarl", "ltda", "cia", "sac", "eirl", "llp", "lp", "nv", "oy", "ab", "as"]);
export const fpNorm = (s: string) => (String(s || "").toLowerCase().match(/[a-z0-9]+/g) || []).filter((x) => !FP_STOP.has(x) && x.length > 1).join(" ").slice(0, 80);
const SHARDS = 32;
let CRC: number[] | null = null;
function crc32(str: string): number {   // same as Python's zlib.crc32 (leads/footprints.py picks the shard with it)
  if (!CRC) { CRC = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; CRC.push(c >>> 0); } }
  let c = 0xffffffff;
  for (const byte of Buffer.from(str, "utf-8")) c = CRC[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function decryptJson<T>(b: Buffer, key: string): T {
  const nonce = b.subarray(0, 12), tag = b.subarray(b.length - 16), body = b.subarray(12, b.length - 16);
  const d = createDecipheriv("aes-256-gcm", Buffer.from(key, "base64"), nonce);
  d.setAuthTag(tag);
  return JSON.parse(gunzipSync(Buffer.concat([d.update(body), d.final()])).toString("utf-8")) as T;
}
async function fpShard(i: number): Promise<Shard | null> {
  const key = process.env.WEB_INDEX_KEY;
  if (!key) return null;
  try { return await load(`footprints/${String(i).padStart(2, "0")}.enc`, (b) => decryptJson<Shard>(b, key)); } catch { return null; }
}
async function fpNames(): Promise<Names | null> {
  const key = process.env.WEB_INDEX_KEY;
  if (!key) return null;
  try { return await load("footprints/names.enc", (b) => decryptJson<Names>(b, key)); } catch { return null; }
}
const shardOf = (k: string) => crc32(k) % SHARDS;
/** Exact normalised name first (one shard); otherwise names holding every word of the query, from the name directory.
 *  size: small (< USD 1M won), mid (1-50M), large (> 50M); empty = any. */
export async function companyFootprint(name: string, n = 3, size = "") {
  const k = fpNorm(name);
  const exact = k ? await fpShard(shardOf(k)) : null;
  if (exact?.companies[k] && (!size || exact.companies[k].sz === size)) return { at: exact.at, rows: [{ key: k, ...exact.companies[k] }] };
  const dir = await fpNames();
  if (!dir) return { at: "", rows: [] as (Footprint & { key: string })[], error: "footprints not built yet" };
  const words = k.split(" ").filter(Boolean);
  const keys = dir.c.filter(([kk, , sz]) => words.length && (!size || sz === size) && words.every((w) => kk.split(" ").includes(w))).sort((a, b) => b[1] - a[1]).slice(0, n).map((x) => x[0]);
  const rows: (Footprint & { key: string })[] = [];
  for (const kk of keys) { const sh = await fpShard(shardOf(kk)); if (sh?.companies[kk]) rows.push({ key: kk, ...sh.companies[kk] }); }
  return { at: dir.at, rows };
}
export async function buyerProfile(name: string, country = "", n = 3) {
  const dir = await fpNames();
  if (!dir) return { at: "", rows: [] as (BuyerProfile & { key: string })[], error: "footprints not built yet" };
  const words = fpNorm(name).split(" ").filter(Boolean);
  const keys = dir.b.filter(([kk]) => { const [nm, c] = kk.split("|"); return words.length && (!country || c === country.toUpperCase()) && words.every((w) => nm.split(" ").includes(w)); })
    .sort((a, b) => b[1] - a[1]).slice(0, n).map((x) => x[0]);
  const rows: (BuyerProfile & { key: string })[] = [];
  for (const kk of keys) { const sh = await fpShard(shardOf(kk.split("|")[0])); if (sh?.buyers[kk]) rows.push({ key: kk, ...sh.buyers[kk] }); }
  return { at: dir.at, rows };
}
