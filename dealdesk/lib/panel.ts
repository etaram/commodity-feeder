import { gunzipSync } from "zlib";
import { createDecipheriv } from "crypto";
import Papa from "papaparse";
import { suppliers as supplierIndex, type Supplier } from "@/lib/index";

const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data";
type Grid = string[][];
type Snap = Record<string, Grid> & { fit?: unknown };
const mem: Record<string, { at: number; data: unknown }> = {};

async function cached<T>(name: string, ttlMs: number, make: () => Promise<T>): Promise<T> {
  const hit = mem[name];
  if (hit && Date.now() - hit.at < ttlMs) return hit.data as T;
  const data = await make();
  mem[name] = { at: Date.now(), data };
  return data;
}

function decrypt(b: Buffer): Buffer {
  const key = process.env.WEB_INDEX_KEY;
  if (!key) throw new Error("WEB_INDEX_KEY is not configured");
  const d = createDecipheriv("aes-256-gcm", Buffer.from(key, "base64"), b.subarray(0, 12));
  d.setAuthTag(b.subarray(b.length - 16));
  return gunzipSync(Buffer.concat([d.update(b.subarray(12, b.length - 16)), d.final()]));
}

async function snapshot(part: "static" | "live"): Promise<Snap> {
  return cached(`snap-${part}`, part === "live" ? 120_000 : 600_000, async () => {
    const r = await fetch(`${RAW}/web/panel_${part}.enc`, { cache: "no-store" });
    if (!r.ok) return {} as Snap;
    return JSON.parse(decrypt(Buffer.from(await r.arrayBuffer())).toString("utf-8")) as Snap;
  });
}

const SUP_COLS: [string, keyof Supplier][] = [["quality", "q"], ["supplier", "n"], ["country", "c"], ["region", "rg"], ["tier", "tr"],
  ["main_sector", "s"], ["other_sectors", "s2"], ["type", "ty"], ["trader", "td"], ["epc", "epc"], ["logistics_role", "lg"],
  ["products", "p"], ["commodities", "cm"], ["exports", "x"], ["wins", "w"], ["won_usd_est", "u"], ["buyer_countries", "bc"],
  ["website", "web"], ["last_win", "lw"], ["tier_reason", "why"]];
const SUP_HEAD = [...SUP_COLS.map(([k]) => k), "sources"];
const supRow = (s: Supplier) => [...SUP_COLS.map(([, k]) => (s[k] == null ? "" : String(s[k]))), "public award records"];

async function allSuppliers(): Promise<Supplier[]> {
  return cached("sup-sorted", 900_000, async () => {
    const { rows, error } = await supplierIndex();
    if (error && !rows.length) throw new Error(error);
    return rows.slice().sort((a, b) => (a.tr || "9").localeCompare(b.tr || "9") || (b.q || 0) - (a.q || 0));
  });
}

async function allTenders(): Promise<{ head: string[]; rows: Record<string, string>[] }> {
  return cached("tenders-full", 900_000, async () => {
    const files = await Promise.all(Array.from({ length: 30 }, (_, i) => fetch(`${RAW}/leads/sheet/tenders_${String(i + 1).padStart(2, "0")}.csv`, { cache: "no-store" })
      .then((r) => (r.ok ? r.text() : "")).catch(() => "")));
    const snap = await snapshot("static");
    const fit = (snap.fit || {}) as Record<string, string[]>;
    let head: string[] = [];
    const rows: Record<string, string>[] = [];
    for (const text of files) {
      if (!text) continue;
      const p = Papa.parse<Record<string, string>>(text, { header: true, skipEmptyLines: true });
      if (!head.length) head = p.meta.fields || [];
      for (const r of p.data) {
        if (!r.id) continue;
        const f = fit[r.id] || [];
        r.fit = f[0] || r.score || ""; r.your_suppliers = f[1] || ""; r.tier_AB = f[2] || "";
        rows.push(r);
      }
    }
    return { head: [...head, "fit", "your_suppliers", "tier_AB"], rows };
  });
}

const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/,/g, "")); return Number.isFinite(n) ? n : NaN; };
const toRe = (p: string) => {
  if (!p) return null;
  try { return new RegExp(p.replace(/\\x\{([0-9a-fA-F]+)\}/g, "\\u{$1}"), "iu"); } catch { return null; }
};

export async function getRange(key: string): Promise<Grid> {
  if (["tenders", "titles", "repeat", "markets", "meta", "upcoming", "tot_t"].includes(key)) return ((await snapshot("static"))[key] as Grid) || [];
  if (["bd", "accounts", "intel", "pursuits", "jobs", "stats"].includes(key)) return ((await snapshot("live"))[key] as Grid) || [];
  if (key === "suppliers") return [SUP_HEAD, ...(await allSuppliers()).slice(0, 6000).map(supRow)];
  if (key === "tot_s") return [["suppliers", String((await allSuppliers()).length)]];
  throw new Error(`unknown range ${key}`);
}

export async function searchTenders(v: string[][]): Promise<Grid> {
  const g = (r: number, c: number) => String((v[r] || [])[c] ?? "").trim();
  const re = toRe(g(0, 0).toLowerCase()), cty = g(0, 2), sec = g(1, 0), lo = num(g(1, 2)), reg = g(2, 0), hi = num(g(2, 2)), dec = g(3, 0), md = num(g(4, 0));
  const { head, rows } = await allTenders();
  const he = new Map(((await snapshot("static")).titles || []).slice(1).map((r) => [r[0], r[1] || ""]));
  const out = rows.filter((r) => {
    if (cty && r.country !== cty) return false;
    if (sec && r.sector !== sec) return false;
    if (reg && r.region !== reg) return false;
    if (dec && r.decision !== dec) return false;
    const val = num(r.est_value_usd);
    if (Number.isFinite(lo) && lo > 0 && !(val >= lo)) return false;
    if (Number.isFinite(hi) && hi > 0 && !(val > 0 && val < hi)) return false;
    const dl = num(r.days_left);
    if (Number.isFinite(md) && md > 0 && r.stage !== "planned" && Number.isFinite(dl) && dl < md) return false;
    if (re && !re.test(`${r.title_en} ${r.title_original} ${he.get(r.id) || ""} ${r.buyer} ${r.commodity} ${r.sector}`.toLowerCase())) return false;
    return true;
  }).sort((a, b) => (num(b.fit) || 0) - (num(a.fit) || 0) || (num(b.ev_usd) || 0) - (num(a.ev_usd) || 0)).slice(0, 2000);
  return [head, ...out.map((r) => head.map((k) => r[k] ?? ""))];
}

const LOGI = /logistic|shipping|freight|port|terminal|courier|warehous|cargo|transport services|trucking/i;
export async function searchSuppliers(v: string[][]): Promise<Grid> {
  const g = (r: number) => String((v[r] || [])[0] ?? "").trim();
  const re = toRe(g(0).toLowerCase()), reg = g(1), cty = g(2), sec = g(3), minq = num(g(4)), needC = g(5) === "yes", role = g(6);
  const out = (await allSuppliers()).filter((s) =>
    (!reg || s.rg === reg) && (!cty || s.c === cty) && (!sec || s.s === sec || (s.s2 || "").includes(sec)) &&
    (!(minq > 0) || (s.q || 0) >= minq) && (!needC || !!s.web) &&
    (!role || (role === "logistics" ? (!!s.lg || LOGI.test(s.s || "")) : role === "trader" ? (s.td === "yes" || /trader/i.test(s.ty || "")) : role === "epc" ? !!s.epc : /goods/i.test(s.ty || ""))) &&
    (!re || re.test(`${s.n} ${s.p || ""} ${s.cm || ""} ${s.s || ""} ${s.s2 || ""} ${s.web || ""} ${s.lg || ""}`.toLowerCase()))).slice(0, 2000);
  return [SUP_HEAD, ...out.map(supRow)];
}
