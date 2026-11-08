import Papa from "papaparse";

// Normalised commodity prices and their statistics (upgrade brief section 11), read-only. The pipeline
// (leads/commodity_norm.py, leads/commodity_stats.py) writes two public CSVs; this module reads them from raw GitHub
// like lib/intel.ts (15-minute cache) and joins them by id. Nothing here compares prices: a futures benchmark is
// never a delivered physical offer, and a row says what it is (price_type, physical, incoterm, delivery, basis).
const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/leads";
type Row = Record<string, string>;
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/[,$]/g, "")); return Number.isFinite(n) ? n : null; };

const mem: Record<string, { at: number; data: Row[] }> = {};
async function csv(name: string): Promise<Row[]> {
  const hit = mem[name];
  if (hit && Date.now() - hit.at < 900_000) return hit.data;
  const r = await fetch(`${RAW}/${name}`, { cache: "no-store" }).catch(() => null);
  const rows = r && r.ok ? (Papa.parse<Row>(await r.text(), { header: true, skipEmptyLines: true }).data || []) : [];
  if (rows.length || !hit) mem[name] = { at: Date.now(), data: rows };
  return rows.length ? rows : hit?.data || [];
}

export type CommodityQuery = { product?: string; hs6?: string; limit?: number };
export type CommodityStat = {
  id: string; hs6: string; product: string; commodity: string; grade: string; origin: string; delivery_location: string; incoterm: string;
  price_usd: number | null; unit: string; price_usd_t: number | null; conversion: string;
  price_type: string; physical: boolean | null; timestamp: string; source: string; source_tier: string; link: string; basis_note: string;
  freq: string; n_points: number; last_date: string; chg_1w_pct: number | null; chg_1m_pct: number | null; chg_3m_pct: number | null; chg_12m_pct: number | null;
  vol_30d: number | null; vol_90d: number | null; season_idx: number[] | null; season_note: string; anomaly: string[]; anomaly_note: string; basis: string;
};

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function joinRows(norm: Row[], stats: Row[], q: CommodityQuery = {}): CommodityStat[] {
  const byId = new Map(stats.map((s) => [s.id, s]));
  const words = String(q.product || "").trim().split(/\s+/).filter(Boolean).map((w) => new RegExp(esc(w), "i"));
  const hs = String(q.hs6 || "").replace(/\D/g, "");
  const limit = Math.min(500, Math.max(1, q.limit || 200));
  const out: CommodityStat[] = [];
  for (const r of norm) {
    if (hs && !String(r.hs6 || "").startsWith(hs)) continue;
    if (words.length && !words.every((w) => w.test(`${r.product} ${r.commodity} ${r.grade} ${r.origin} ${r.delivery_location} ${r.source}`))) continue;
    const s = byId.get(r.id) || {};
    let season: number[] | null = null;
    try { season = s.season_idx ? (JSON.parse(s.season_idx) as number[]) : null; } catch { season = null; }
    out.push({
      id: r.id, hs6: r.hs6 || "", product: r.product || "", commodity: r.commodity || "", grade: r.grade || "", origin: r.origin || "",
      delivery_location: r.delivery_location || "", incoterm: r.incoterm || "", price_usd: num(r.price_usd), unit: r.unit_canonical || r.unit || "",
      price_usd_t: num(r.price_usd_t), conversion: r.conversion || "", price_type: r.price_type_norm || "unknown",
      physical: r.physical === "true" ? true : r.physical === "false" ? false : null, timestamp: r.timestamp || "", source: r.source || "",
      source_tier: r.source_tier || "", link: r.link || "", basis_note: r.basis_note || "",
      freq: s.freq || "", n_points: num(s.n_points) || 0, last_date: s.last_date || "", chg_1w_pct: num(s.chg_1w_pct), chg_1m_pct: num(s.chg_1m_pct),
      chg_3m_pct: num(s.chg_3m_pct), chg_12m_pct: num(s.chg_12m_pct), vol_30d: num(s.vol_30d), vol_90d: num(s.vol_90d), season_idx: season,
      season_note: s.season_note || "", anomaly: String(s.anomaly || "").split(";").filter(Boolean), anomaly_note: s.anomaly_note || "", basis: s.basis || "",
    });
    if (out.length >= limit) break;
  }
  return out;
}

// World Bank Pink Sheet monthly series (ids "WB:<series>") carry their own stats rows and no normalised price row
export function pinkSheet(stats: Row[]) {
  return stats.filter((s) => String(s.id || "").startsWith("WB:")).map((s) => {
    let season: number[] | null = null;
    try { season = s.season_idx ? (JSON.parse(s.season_idx) as number[]) : null; } catch { season = null; }
    return { id: s.id, name: s.name || "", last_date: s.last_date || "", last_price: num(s.last_price), chg_1m_pct: num(s.chg_1m_pct), chg_3m_pct: num(s.chg_3m_pct),
      chg_12m_pct: num(s.chg_12m_pct), season_idx: season, season_note: s.season_note || "", anomaly: String(s.anomaly || "").split(";").filter(Boolean), basis: s.basis || "" };
  });
}

export async function commodityStats(q: CommodityQuery = {}) {
  const [norm, stats] = await Promise.all([csv("commodity_prices_norm.csv"), csv("commodity_stats.csv")]);
  const items = joinRows(norm, stats, q);
  const counts = { total: norm.length, matched: items.length, physical: items.filter((i) => i.physical === true).length,
    futures: items.filter((i) => i.price_type === "futures").length, anomalies: items.filter((i) => i.anomaly.length).length };
  return { items, worldbank: q.product || q.hs6 ? [] : pinkSheet(stats), counts,
    note: "Prices are shown on their own basis (price_type, incoterm, delivery, unit). A futures benchmark or a trade unit value is not a delivered physical offer; compare only after landed cost on the same specification." };
}
