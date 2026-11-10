import { supplierSearch } from "@/lib/panel";
import { appendRow, readRanges, ENGINE_SHEET } from "@/lib/sheets";

// Coverage-gap radar (spec phases 2 and 9): for the priority products of the system's sectors, how many suppliers the
// search can support with evidence, how many only plausibly, how many are verified on an authoritative source, from
// how many origin countries, and how many can be reached (website on record). Database size is not market coverage:
// a product with few supported suppliers or a single origin is a gap to research first, and a strong candidate
// without a reachable channel is the next enrichment task. Computed from the live search code, cached 6 hours.
export const PRIORITY: { family: string; q: string }[] = [
  ["Commodities", "wheat"], ["Commodities", "rice"], ["Commodities", "sugar"], ["Commodities", "white maize"], ["Commodities", "sunflower oil"],
  ["Commodities", "milk powder"], ["Commodities", "frozen tuna"], ["Commodities", "granular urea fertilizer"], ["Commodities", "ammonia"],
  ["Commodities", "cement"], ["Commodities", "steel rebar"], ["Commodities", "hot rolled steel coil"], ["Commodities", "copper cable"],
  ["Energy", "jet fuel"], ["Energy", "LPG"], ["Energy", "bitumen"], ["Energy", "diesel generator"], ["Energy", "solar panels"],
  ["Energy", "power transformer"], ["Energy", "distribution transformer"], ["Energy", "lithium battery storage"],
  ["Water", "PE pipes and fittings"], ["Water", "ductile iron pipe"], ["Water", "water meters"], ["Water", "reverse osmosis"],
  ["Data centers", "UPS uninterruptible power supply"], ["Data centers", "server racks"], ["Data centers", "data center cooling"],
  ["Defence", "ammunition"], ["Defence", "body armour"], ["Defence", "night vision"],
  ["Health", "X-ray machine"], ["Health", "patient monitors"], ["Health", "surgical gloves"],
  ["Infrastructure", "excavator"], ["Infrastructure", "fire trucks"],
].map(([family, q]) => ({ family, q }));

type Row = { family: string; product: string; total: number; supported: number; plausible: number; verified: number; origins: number; top_origins: string; reachable_supported: number; gap: string; next: string };
let mem: { at: number; rows: Row[] } | null = null;

// The count takes about a minute (36 searches over the whole index), so the last result is kept in the state sheet
// (hidden tab "Coverage Cache", one JSON cell per run): a cold start answers from it at once and a result older than
// 6 hours is recomputed on the request that finds it stale ("fresh=1" always recomputes).
async function stored(): Promise<{ at: number; rows: Row[] } | null> {
  try {
    const v = (await readRanges(ENGINE_SHEET, ["'Coverage Cache'!A1:B400"]))?.[0] || [];
    for (let i = v.length - 1; i >= 0; i--) { const at = Date.parse(String(v[i][0] || "")); if (isFinite(at) && v[i][1]) return { at, rows: JSON.parse(String(v[i][1])) as Row[] }; }
  } catch { /* no cache yet */ }
  return null;
}
let running: Promise<Row[]> | null = null;
export async function coverage(fresh = false): Promise<Row[]> {
  if (!fresh && mem && Date.now() - mem.at < 6 * 3600e3) return mem.rows;
  if (!fresh) {
    const st = await stored();
    if (st && st.rows.length) {
      mem = st;
      if (Date.now() - st.at < 6 * 3600e3) return st.rows;
      if (!running) running = compute().finally(() => { running = null; });   // stale: shown now, refreshed for the next request
      void running.catch(() => {});
      return st.rows;
    }
  }
  if (!running) running = compute().finally(() => { running = null; });
  return running;
}
async function compute(): Promise<Row[]> {
  const rows: Row[] = [];
  // counts come from the search code itself (no model call per product: the page must answer in seconds, also on a cold start)
  const found: Awaited<ReturnType<typeof supplierSearch>>[] = [];
  for (let i = 0; i < PRIORITY.length; i += 6) found.push(...(await Promise.all(PRIORITY.slice(i, i + 6).map((p) => supplierSearch({ text: p.q, n: 100, strict: true, noExpand: true }).catch(() => null as never)))));
  for (const [k, p] of PRIORITY.entries()) {
    const r = found[k];
    if (!r) continue;
    const [h, ...vals] = r.values as string[][];
    const ix = (k: string) => h.indexOf(k);
    const sup = vals.filter((x) => x[ix("match")] === "supported");
    const ver = vals.filter((x) => /verified/.test(String(x[ix("match_evidence")] || "")) && x[ix("match")] === "supported");
    const plaus = vals.filter((x) => x[ix("match")] === "plausible");
    const orig = new Map<string, number>();
    for (const x of sup) orig.set(x[ix("country")], (orig.get(x[ix("country")]) || 0) + 1);
    const reach = sup.filter((x) => x[ix("website")]).length;
    const gap = sup.length < 5 ? "few supported suppliers" : orig.size < 3 ? "few origin countries" : ver.length === 0 ? "none verified yet" : reach < sup.length / 2 ? "most cannot be reached yet" : "";
    const next = gap === "few supported suppliers" ? "research producers of this product (web research)" : gap === "few origin countries" ? "find suppliers in other origins" : gap === "none verified yet" ? "verify the top supported suppliers" : gap ? "find contact channels for the supported suppliers" : "";
    rows.push({ family: p.family, product: p.q, total: r.total, supported: sup.length, plausible: plaus.length, verified: ver.length, origins: orig.size,
      top_origins: [...orig.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([c, n]) => `${c} ${n}`).join(", "), reachable_supported: reach, gap, next });
  }
  mem = { at: Date.now(), rows };
  await appendRow("Coverage Cache", [new Date().toISOString(), JSON.stringify(rows).slice(0, 49000)]).catch(() => {});
  return rows;
}
