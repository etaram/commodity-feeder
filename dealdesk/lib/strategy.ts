import { DEFAULT_WS } from "@/lib/auth";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { ownWorkspace, scrubTendersForWs } from "@/lib/scope";

// Per-workspace strategy (spec section 15): another organisation's own partner countries, focus sectors and
// excluded markets, applied at read time on top of the shared tender list (which is ranked once with the original
// workspace's strategy and scrubbed of it for everyone else). Stored append-only in the hidden tab
// 'Workspace strategy' (A workspace, B updated, C JSON, D by); the latest row per workspace wins.
export type Strategy = { partners: string[]; focus: string[]; excluded: string[] };
const TAB = "Workspace strategy";
// Fixed bonuses, not measured effects: each one is named with its size in the fit_why text the user reads.
const PARTNER_POINTS = 5; // leads/dealfit.py W["partner"]
const FOCUS_POINTS = 3;
const iso = (v: unknown) => (Array.isArray(v) ? v : []).map((x) => String(x || "").trim().toUpperCase()).filter((c) => /^[A-Z]{3}$/.test(c)).slice(0, 80);
const words = (v: unknown) => (Array.isArray(v) ? v : []).map((x) => String(x || "").trim().slice(0, 60)).filter(Boolean).slice(0, 30);
export const cleanStrategy = (o: Record<string, unknown> = {}): Strategy => ({ partners: iso(o.partners), focus: words(o.focus), excluded: iso(o.excluded) });

let cache: { at: number; by: Map<string, Strategy> } | null = null;
export async function strategies(fresh = false): Promise<Map<string, Strategy>> {
  if (!fresh && cache && Date.now() - cache.at < 300_000) return cache.by;
  const v = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:D2000`]).catch(() => null))?.[0] || [];
  const by = new Map<string, Strategy>();
  for (const r of v) { const ws = String(r[0] || "").trim(); if (!ws) continue; try { by.set(ws, cleanStrategy(JSON.parse(String(r[2] || "{}")))); } catch { /* skip a broken row */ } }
  cache = { at: Date.now(), by };
  return by;
}
export async function getStrategy(ws: string) { return (await strategies()).get(ws) || null; }
export async function saveStrategy(ws: string, st: Strategy, by: string) {
  await appendRow(TAB, [ws, new Date().toISOString(), JSON.stringify(st), by]);
  cache = null;
}

// Pure: the shared grid as this workspace should see it.
export function applyStrategy(grid: string[][], ws: string, st: Strategy | null): string[][] {
  const g = scrubTendersForWs(grid, ws);
  if (ownWorkspace(ws) || !st || !g.length) return g;
  const h = g[0], ic = h.indexOf("country"), iw = h.indexOf("fit_why"), isc = h.indexOf("score"), ifit = h.indexOf("fit"), isec = h.indexOf("sector");
  const part = new Set(st.partners), excl = new Set(st.excluded), focus = st.focus.map((f) => f.toLowerCase());
  const out = [h];
  for (const r of g.slice(1)) {
    const c = ic >= 0 ? String(r[ic] || "") : "";
    if (excl.has(c)) continue;
    let add = 0; const why: string[] = [];
    if (part.has(c)) { add += PARTNER_POINTS; why.push(`local partner (your workspace): fixed +${PARTNER_POINTS} points`); }
    if (isec >= 0 && focus.length && focus.some((f) => String(r[isec] || "").toLowerCase().includes(f))) { add += FOCUS_POINTS; why.push(`focus sector (your workspace): fixed +${FOCUS_POINTS} points`); }
    if (!add) { out.push(r); continue; }
    const x = [...r];
    for (const k of [isc, ifit]) if (k >= 0 && x[k] !== "" && Number.isFinite(Number(x[k]))) x[k] = String(Math.min(100, Number(x[k]) + add));
    if (iw >= 0) x[iw] = [String(x[iw] || ""), ...why].filter(Boolean).join("; ");
    out.push(x);
  }
  return out;
}
export async function tendersForWs(grid: string[][], ws: string) {
  return ownWorkspace(ws) ? grid : applyStrategy(grid, ws, await getStrategy(ws).catch(() => null));
}
export { DEFAULT_WS };
