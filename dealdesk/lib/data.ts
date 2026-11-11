import { RAW_ROOT } from "@/lib/rawbase";
import Papa from "papaparse";

const RAW = `${RAW_ROOT}`;
const TTL = 900;

export type Row = Record<string, string>;

async function csv(path: string, revalidate = TTL): Promise<Row[]> {
  try {
    const r = await fetch(`${RAW}/${path}`, { next: { revalidate } });
    if (!r.ok) return [];
    const text = await r.text();
    const out = Papa.parse<Row>(text, { header: true, skipEmptyLines: true });
    return (out.data || []).filter((x) => Object.values(x).some(Boolean));
  } catch {
    return [];
  }
}

export const num = (v: string | undefined) => {
  const n = parseFloat(v || "");
  return Number.isFinite(n) ? n : 0;
};

export const usd = (v: number) =>
  v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${Math.round(v)}`;

export const pct = (v: string | undefined, digits = 0) => {
  const n = parseFloat(v || "");
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "-";
};

export const getDeals = () => csv("data/leads/deal_calc.csv");
export const getPress = () => csv("data/leads/press.csv");
export const getIsrael = () => csv("data/israel/items.csv");
export const getCountries = () => csv("data/leads/countries.csv");
export const getSectors = () => csv("data/leads/sectors.csv");
export const getSources = () => csv("data/leads/status.csv");
export const getSourceQuality = () => csv("data/leads/source_quality.csv");
export const getTrends = () => csv("data/leads/price_trends.csv");
export const getBuyers = () => csv("data/leads/buyers.csv");
export const getAwards = () => csv("data/leads/awards.csv");
export const getGrants = () => csv("data/leads/grants.csv");
export const getExempt = () => csv("data/leads/exempt.csv");
export const getIlExempt = () => csv("data/leads/il_exempt.csv");
export const getGovernance = () => csv("data/leads/governance.csv");

export async function getDeal(id: string): Promise<Row | undefined> {
  const deals = await getDeals();
  return deals.find((d) => d.id === id);
}

export const ROUTE_LABEL: Record<string, string> = {
  direct: "Direct bid",
  "via local partner": "Via local partner",
  "needs local partner": "Needs a local partner",
  "sub-supply to the winner": "Sub-supply to the winner",
};

export type PriceItem = { id: string; name: string; hs6: string; price: number; unit: string; date: string; source: string; tier: string; link: string; chg: Record<string, number | null>; chg_src: string };
export type PriceData = { updated_utc: string; feed_finished_utc: string; count: number; items: PriceItem[]; worldbank: { group: string; name: string; unit: string; month: string; price: number; chg: Record<string, number | null> }[] };
export async function getPriceChanges(): Promise<PriceData | null> {
  try {
    const r = await fetch(`${RAW}/data/leads/price_changes.json`, { next: { revalidate: 300 } });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

// Per-source status of the collectors (data/leads/source_status.json, written on every run by leads/source_status.py):
// a failed, refused, throttled, empty, halved or stale source is listed as such and never as a success.
export type SourceStatus = { source: string; status: string; rows: number; rows_last_good: number; last_good_at: string; last_run_at?: string; error_class?: string; warning?: string; cadence_h?: number; age_h?: number | null };
export type SourceStatusFile = { generated: string; not_ok: number; sources: SourceStatus[]; merge?: Partial<SourceStatus> };
export const SOURCE_STATUS_LABEL: Record<string, string> = {
  OK: "OK", DEGRADED: "Degraded: empty or far fewer rows", STALE: "Stale: no good run within its schedule", DOWN: "Down: the collector failed",
  DENIED: "Denied: the site refused access", RATE_LIMITED: "Rate limited: the site throttled us",
};
const STATUS_ORDER = ["DOWN", "DENIED", "RATE_LIMITED", "STALE", "DEGRADED", "OK"];
/** Sources that are not OK first (worst first), then by name. An unknown status is treated as not OK. */
export function sortSourceStatus(list: SourceStatus[]): SourceStatus[] {
  const rank = (s: SourceStatus) => { const i = STATUS_ORDER.indexOf(s.status); return i < 0 ? 0 : i; };
  return [...list].sort((a, b) => rank(a) - rank(b) || a.source.localeCompare(b.source));
}
export async function getSourceStatus(): Promise<SourceStatusFile | null> {
  try {
    const r = await fetch(`${RAW}/data/leads/source_status.json`, { next: { revalidate: 300 } });
    if (!r.ok) return null;
    const j = await r.json();
    return j && Array.isArray(j.sources) ? { generated: String(j.generated || ""), not_ok: Number(j.not_ok) || 0, sources: sortSourceStatus(j.sources), merge: j.merge || undefined } : null;
  } catch { return null; }
}
