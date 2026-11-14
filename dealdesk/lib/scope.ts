import { DEFAULT_WS } from "@/lib/auth";

// Data scopes (spec section 15): reusable public knowledge, organisation-private information, user-private state.
// The sheet tabs below are the original workspace's private records (its buyers, pursuits, research jobs, contacts,
// projects, intelligence notes and watchlist). Another workspace gets an empty grid for them and cannot write to
// them; public collections (tenders, suppliers, markets, plays, grants) are shared. Deny by default: a new tab is
// private until it is added to PUBLIC_KEYS.
export const PUBLIC_KEYS = new Set(["biztrends", "ais", "portwatch", "tenders", "titles", "repeat", "markets", "plays", "fx", "meta", "upcoming", "stats",
  "suppliers", "grants", "exempt", "ilex", "integrity", "tot_t", "tot_s", "websup"]);
export const ownWorkspace = (ws: string) => ws === DEFAULT_WS;
export function canRead(ws: string, key: string): boolean {
  return ownWorkspace(ws) || PUBLIC_KEYS.has(key);
}
export const canWriteOwnerTabs = (ws: string) => ownWorkspace(ws);

// The shared tender ranking is computed once with the original workspace's strategy (its partner countries add
// points). Another organisation must not inherit that: the partner credit is taken out of the score and the reason
// line for it, and the row says which strategy ranked it. Evidence and penalties are untouched.
const PARTNER_POINTS = 5; // leads/dealfit.py W["partner"]
export function scrubTendersForWs(grid: string[][], ws: string): string[][] {
  if (ownWorkspace(ws) || !grid.length) return grid;
  const h = grid[0], iw = h.indexOf("fit_why"), isc = h.indexOf("score"), ifit = h.indexOf("fit");
  return [h, ...grid.slice(1).map((r) => {
    const why = iw >= 0 ? String(r[iw] || "") : "";
    if (!/local partner/.test(why)) return r;
    const x = [...r];
    x[iw] = why.replace(/;?\s*local partner/g, "").trim();
    for (const k of [isc, ifit]) if (k >= 0 && x[k] !== "" && Number.isFinite(Number(x[k]))) x[k] = String(Math.max(0, Number(x[k]) - PARTNER_POINTS));
    return x;
  })];
}
