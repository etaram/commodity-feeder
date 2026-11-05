import Papa from "papaparse";

// World and project intelligence (spec phase 4), read-only. The pipeline (leads/events.py, leads/hypotheses.py)
// writes three public CSVs; this module reads them from raw GitHub like lib/focus.ts and shapes three outputs:
//   events      world intelligence: typed events with country roles, verification and the per-event analysis
//   timelines   projects that link funding, plans, packages, tenders and awards
//   hypotheses  research candidates (gaps stated) and actionable ones (an open tender exists); all are hypotheses
const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/leads";
type Row = Record<string, string>;
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/[,$]/g, "")); return Number.isFinite(n) ? n : 0; };

const mem: Record<string, { at: number; data: Row[] }> = {};
async function csv(name: string): Promise<Row[]> {
  const hit = mem[name];
  if (hit && Date.now() - hit.at < 900_000) return hit.data;
  const r = await fetch(`${RAW}/${name}`, { cache: "no-store" }).catch(() => null);
  const rows = r && r.ok ? (Papa.parse<Row>(await r.text(), { header: true, skipEmptyLines: true }).data || []) : [];
  if (rows.length || !hit) mem[name] = { at: Date.now(), data: rows };
  return rows.length ? rows : hit?.data || [];
}

export type IntelQuery = { country?: string; type?: string; origin?: string; tier?: string };
const EV_FIELDS = ["event_id", "type", "tags", "related_projects", "change", "change_note", "event_date", "first_seen", "last_seen", "title", "summary", "project_country",
  "buyer_country", "supplier_country", "publisher_country", "affected_markets", "value_usd", "buyer", "supplier", "actors", "sector", "project_key",
  "project_ref", "link_basis", "tender_id", "origin", "sources", "independent_sources", "mirrors", "republished_count", "url", "verified", "inferred",
  "what_changed", "why_matters", "sinder_angle", "confirm_by", "monitor_next", "tier"];
const pick = (r: Row, f: string[]) => Object.fromEntries(f.map((k) => [k, r[k] ?? ""]));
const TIER: Record<string, number> = { high: 2, medium: 1, low: 0 };

const codes = (s: string | undefined) => String(s || "").toUpperCase().split(/[,\s;]+/).filter(Boolean);
// an event touches a country when it is the project, buyer or supplier country, or an affected market
export function touches(r: Row, cs: string[]): boolean {
  if (!cs.length) return true;
  const mine = new Set([r.project_country, r.buyer_country, r.supplier_country, ...String(r.affected_markets || "").split(";")].map((x) => String(x || "").toUpperCase()));
  return cs.some((c) => mine.has(c));
}

export function filterEvents(rows: Row[], q: IntelQuery, limit = 60) {
  const cs = codes(q.country), ts = String(q.type || "").split(",").map((x) => x.trim()).filter(Boolean);
  const minTier = TIER[String(q.tier || "low")] ?? 0;
  return rows
    .filter((r) => touches(r, cs) && (!ts.length || ts.includes(r.type)) && (!q.origin || r.origin === q.origin) && (TIER[r.tier] ?? 0) >= minTier)
    .sort((a, b) => String(b.event_date).localeCompare(String(a.event_date)) || (TIER[b.tier] ?? 0) - (TIER[a.tier] ?? 0) || num(b.value_usd) - num(a.value_usd))
    .slice(0, limit)
    .map((r) => pick(r, EV_FIELDS));
}

// recency (last 180 days) and size (value, number of linked events) in one score
export function timelineScore(r: Row, now = Date.now()): number {
  const d = Date.parse(r.last_date || "");
  const days = Number.isFinite(d) ? Math.max(0, (now - d) / 86_400_000) : 365;
  const rec = Math.max(0, 1 - days / 180);
  const size = Math.min(1, Math.log10(num(r.value_usd) + 1) / 10) * 0.7 + Math.min(1, num(r.n_events) / 20) * 0.3;
  return 0.55 * rec + 0.45 * size;
}

export function rankTimelines(rows: Row[], q: IntelQuery, limit = 30, now = Date.now()) {
  const cs = codes(q.country);
  return rows
    .filter((r) => !cs.length || cs.includes(String(r.project_country || "").toUpperCase()))
    .map((r) => ({ r, s: timelineScore(r, now) }))
    .sort((a, b) => b.s - a.s)
    .slice(0, limit)
    .map(({ r, s }) => {
      let milestones: unknown[] = [];
      try { milestones = JSON.parse(r.milestones || "[]"); } catch { milestones = []; }
      const out: Record<string, unknown> = { ...r, score: Math.round(s * 1000) / 1000, milestones };
      return out;
    });
}

export function splitHypotheses(rows: Row[], q: IntelQuery, limit = 40, today = new Date().toISOString().slice(0, 10)) {
  const cs = codes(q.country);
  const ok = rows.filter((r) => !cs.length || cs.includes(String(r.project_country || "").toUpperCase()));
  // an open tender whose deadline has passed since the last pipeline run is no longer actionable
  const actionable = ok.filter((r) => r.status === "actionable" && (!r.tender_deadline || r.tender_deadline >= today));
  const research = ok.filter((r) => r.status === "research candidate");
  return { research: research.slice(0, limit), actionable: actionable.slice(0, limit), counts: { research: research.length, actionable: actionable.length } };
}

export async function intel(q: IntelQuery) {
  const [ev, tl, hy] = await Promise.all([csv("events.csv"), csv("project_timelines.csv"), csv("hypotheses.csv")]);
  const types: Record<string, number> = {};
  for (const r of ev) types[r.type] = (types[r.type] || 0) + 1;
  const h = splitHypotheses(hy, q);
  return {
    events: filterEvents(ev, q),
    timelines: rankTimelines(tl, q),
    hypotheses: { research: h.research, actionable: h.actionable },
    counts: { events: ev.length, timelines: tl.length, research: h.counts.research, actionable: h.counts.actionable, types },
    note: "Hypotheses are not recommendations: research candidates carry stated gaps; actionable means an open tender exists, not that it fits.",
  };
}
