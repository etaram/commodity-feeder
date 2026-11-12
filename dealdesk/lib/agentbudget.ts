// A hard spend cap shared by every agent role. Unlike AI_DAILY_BUDGET_USD (lib/anthropic.ts), which is an alert line,
// this one refuses: a role reserves the worst-case cost of ONE model call before making it and the call is not made
// when the reservation is refused. Nothing is queued for later.
//
// The owner's decision (environment, with defaults):
//   AGENT_BUDGET_DAY_USD   1            per calendar day in Asia/Jerusalem
//   AGENT_BUDGET_TOTAL_USD 5            cumulative over the period
//   AGENT_BUDGET_FROM      2026-11-12   first day of the period (Asia/Jerusalem, inclusive)
//   AGENT_BUDGET_UNTIL     2026-11-14   last day of the period (inclusive); outside the period every call is refused
//
// The ledger is append-only (tab 'Agent Budget' in the state sheet). Rows: reserve (worst case), settle (actual cost,
// or "unknown"), release (a reservation that lost the race below). What a reservation counts for:
//   released                      0
//   settled with a known cost     the actual cost
//   anything else                 the reserved worst case (not settled yet, or settled as unknown)
// A reservation belongs to the day it was made on, also when it is settled after midnight.
//
// Amounts are "estimated": the same list prices as the 'AI Usage' ledger (estimateCost). The provider's invoice is the
// only measured figure. If ANTHROPIC_MODEL is changed without AI_PRICE_IN / AI_PRICE_OUT, the estimate is wrong;
// lib/pipeline.ts refuses real runs in that state (pricesKnown).
import { randomUUID } from "crypto";
import { estimateCost } from "@/lib/anthropic";
import { appendRow, ENGINE_SHEET, readRanges, sheetsEnabled } from "@/lib/sheets";

export const AGENT_BUDGET_TAB = "Agent Budget";
export type BudgetRow = { time: string; token: string; kind: "reserve" | "settle" | "release"; run: string; role: string; usd: number | null; note: string };
export interface BudgetStore { list(): Promise<BudgetRow[]>; append(row: BudgetRow): Promise<void> }
export type RefuseReason = "day_cap" | "total_cap" | "outside_period" | "unbounded" | "ledger_unreadable";
export type Reservation = { ok: true; token: string; reservedUsd: number } | { ok: false; reason: RefuseReason };
export type BudgetConfig = { dayUsd: number; totalUsd: number; from: string; until: string };

// A cap that is set but unreadable counts as 0 (refuse everything), never as the default: a typo must not open the tap.
const envCap = (k: string, d: number) => { const v = process.env[k]; if (v === undefined || v.trim() === "") return d; const n = Number(v); return Number.isFinite(n) && n >= 0 ? n : 0; };
const envDay = (k: string, d: string) => { const v = (process.env[k] || "").trim(); return v === "" ? d : /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : ""; };
export function budgetConfig(): BudgetConfig {
  return { dayUsd: envCap("AGENT_BUDGET_DAY_USD", 1), totalUsd: envCap("AGENT_BUDGET_TOTAL_USD", 5), from: envDay("AGENT_BUDGET_FROM", "2026-11-12"), until: envDay("AGENT_BUDGET_UNTIL", "2026-11-14") };
}

const DAY_FMT = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem", year: "numeric", month: "2-digit", day: "2-digit" });
/** The calendar day in Asia/Jerusalem (YYYY-MM-DD) of a moment; "" when the moment cannot be read. */
export function jerusalemDay(t: number | string): string {
  const ms = typeof t === "number" ? t : Date.parse(t);
  return Number.isFinite(ms) ? DAY_FMT.format(new Date(ms)) : "";
}
const inPeriod = (day: string, c: BudgetConfig) => !!day && !!c.from && !!c.until && day >= c.from && day <= c.until;
// Sums are compared in whole micro-dollars so that 3 x 0.30 against 1.00 does not depend on floating point.
const micro = (usd: number) => Math.round(usd * 1e6);

/** Worst-case cost of one model call from its hard limits, at the prices of lib/anthropic.ts. Infinity when a limit is missing. */
export function worstCase(o: { maxInputTokens: number; maxOutputTokens: number; maxSearches?: number }): number {
  const s = o.maxSearches ?? 0;
  if (![o.maxInputTokens, o.maxOutputTokens, s].every((n) => typeof n === "number" && Number.isFinite(n) && n >= 0)) return Infinity;
  return estimateCost({ input_tokens: Math.ceil(o.maxInputTokens), output_tokens: Math.ceil(o.maxOutputTokens), server_tool_use: { web_search_requests: Math.ceil(s) } });
}

// ---- reading the ledger ------------------------------------------------------------------------------------
type Entry = { token: string; pos: number; day: string; reserved: number; settled: number | null; released: boolean };
/** One entry per reservation, in ledger order. Throws on a reserve row that cannot be read: an unreadable row is never counted as 0. */
function entries(rows: BudgetRow[]): Entry[] {
  const by = new Map<string, Entry>(), out: Entry[] = [];
  rows.forEach((r, pos) => {
    if (r.kind === "reserve") {
      const day = jerusalemDay(r.time);
      if (!r.token || !day || typeof r.usd !== "number" || !Number.isFinite(r.usd) || r.usd <= 0) throw new Error(`budget ledger row ${pos + 1} cannot be read`);
      if (by.has(r.token)) return; // a token is reserved once; a repeated row adds nothing
      const e: Entry = { token: r.token, pos, day, reserved: r.usd, settled: null, released: false };
      by.set(r.token, e); out.push(e);
    }
  });
  // settle and release rows are applied wherever they stand: a row can only lower a count for a token that reserved
  for (const r of rows) {
    const e = by.get(r.token);
    if (!e) continue;
    if (r.kind === "release") e.released = true;
    if (r.kind === "settle" && typeof r.usd === "number" && Number.isFinite(r.usd) && r.usd >= 0) e.settled = r.usd;
  }
  return out;
}
const counted = (e: Entry) => (e.released ? 0 : e.settled ?? e.reserved);

// ---- reserve -----------------------------------------------------------------------------------------------
// Concurrency: append, then verify. Two roles that start at the same moment both append a reservation row and both
// read the ledger back. Each keeps its reservation only if the rows that stand BEFORE its own row in the ledger, plus
// its own, fit under both caps; the one that does not fit appends a release row and is refused. Whatever landed before
// my row had landed before my own append returned, so my read-back sees it; rows after mine are judged by their own
// owners, who see mine. So of two rows that cannot both fit, the later one always loses, and nobody needs a lock.
//
// The order used is the ledger's own order (the position list() returns), not the time written in the row. The task
// note said (time, token); that order is decided by each writer's clock before its append lands, and a writer with an
// earlier stamp whose append lands late would be invisible to a later-stamped writer that already verified: both
// would pass. Position has no such gap.
//
// The limit, stated plainly: this relies on the ledger (a) showing my own row in the read that follows my append,
// (b) returning rows in one stable order to every reader, and (c) never dropping or overwriting an appended row.
// Google Sheets appends are serialised per spreadsheet and have behaved that way here, but none of the three is a
// documented guarantee. If my row is missing from the read-back the reservation is refused (ledger_unreadable). A
// refused row that is still waiting for its release row counts until then, so under contention a call that would
// have fitted can be refused; the error is always on the side of spending less.
export async function reserve(store: BudgetStore, a: { run: string; role: string; worstCaseUsd: number; now: number }, cfg: BudgetConfig = budgetConfig()): Promise<Reservation> {
  const usd = a.worstCaseUsd;
  if (typeof usd !== "number" || !Number.isFinite(usd) || usd <= 0) return { ok: false, reason: "unbounded" };
  const day = jerusalemDay(a.now);
  if (!inPeriod(day, cfg)) return { ok: false, reason: "outside_period" };
  // a cheap look first: a call that cannot fit writes nothing (and an unreadable ledger is found before any row is added)
  let before: Entry[];
  try { before = entries(await store.list()); } catch { return { ok: false, reason: "ledger_unreadable" }; }
  const fits = (list: Entry[]): RefuseReason | null => {
    const sum = (f: (e: Entry) => boolean) => list.filter(f).reduce((s, e) => s + micro(counted(e)), 0);
    if (sum((e) => e.day === day) + micro(usd) > micro(cfg.dayUsd)) return "day_cap";
    if (sum((e) => inPeriod(e.day, cfg)) + micro(usd) > micro(cfg.totalUsd)) return "total_cap";
    return null;
  };
  const early = fits(before);
  if (early) return { ok: false, reason: early };

  const token = randomUUID(), time = new Date(a.now).toISOString();
  const base = { token, run: String(a.run || "").slice(0, 80), role: String(a.role || "").slice(0, 40) };
  try { await store.append({ ...base, time, kind: "reserve", usd, note: "" }); } catch { return { ok: false, reason: "ledger_unreadable" }; }
  // From here a row of ours is (or may be) in the ledger: every refusal below also writes a release row. If that
  // write fails too, the row stays counted at the worst case, which is the safe direction.
  const giveUp = async (reason: RefuseReason): Promise<Reservation> => {
    await store.append({ ...base, time: new Date(a.now).toISOString(), kind: "release", usd: null, note: reason }).catch(() => {});
    return { ok: false, reason };
  };
  let after: Entry[];
  try { after = entries(await store.list()); } catch { return giveUp("ledger_unreadable"); }
  const mine = after.find((e) => e.token === token);
  if (!mine) return giveUp("ledger_unreadable");
  const late = fits(after.filter((e) => e.pos < mine.pos));
  if (late) return giveUp(late);
  return { ok: true, token, reservedUsd: usd };
}

/** Records what a reserved call really cost. Unknown cost (the call failed mid-way, usage missing): pass null, and the
 *  reservation stays counted at its worst case. A retry of the call is a new reserve(). */
export async function settle(store: BudgetStore, token: string, actualUsd: number | null | undefined, now: number): Promise<{ ok: boolean; known: boolean }> {
  const known = typeof actualUsd === "number" && Number.isFinite(actualUsd) && actualUsd >= 0;
  try {
    await store.append({ time: new Date(now).toISOString(), token, kind: "settle", run: "", role: "", usd: known ? (actualUsd as number) : null, note: known ? "" : "unknown: counted at the reserved worst case" });
    return { ok: true, known };
  } catch { return { ok: false, known }; } // not recorded: the reservation stays at the worst case
}

// ---- display -----------------------------------------------------------------------------------------------
export type BudgetView = { readable: boolean; day: string; in_period: boolean; from: string; until: string; day_cap_usd: number; total_cap_usd: number;
  today: { spent_usd: number; reserved_usd: number }; total: { spent_usd: number; reserved_usd: number }; remaining_today_usd: number; remaining_total_usd: number; remaining_usd: number; estimated: true };
/** Spent (settled, known) and reserved (still counted at the worst case) today and over the period, and what is left. */
export async function budgetView(store: BudgetStore, now: number, cfg: BudgetConfig = budgetConfig()): Promise<BudgetView> {
  const day = jerusalemDay(now), inP = inPeriod(day, cfg);
  const v: BudgetView = { readable: false, day, in_period: inP, from: cfg.from, until: cfg.until, day_cap_usd: cfg.dayUsd, total_cap_usd: cfg.totalUsd,
    today: { spent_usd: 0, reserved_usd: 0 }, total: { spent_usd: 0, reserved_usd: 0 }, remaining_today_usd: 0, remaining_total_usd: 0, remaining_usd: 0, estimated: true };
  let list: Entry[];
  try { list = entries(await store.list()); } catch { return v; } // unreadable: nothing is left to spend
  const t = { ds: 0, dr: 0, ts: 0, tr: 0 };
  for (const e of list) {
    if (e.released || !inPeriod(e.day, cfg)) continue;
    const spent = e.settled !== null ? micro(e.settled) : 0, held = e.settled !== null ? 0 : micro(e.reserved);
    t.ts += spent; t.tr += held;
    if (e.day === day) { t.ds += spent; t.dr += held; }
  }
  const left = (cap: number, used: number) => (inP ? Math.max(0, micro(cap) - used) / 1e6 : 0);
  v.readable = true;
  v.today = { spent_usd: t.ds / 1e6, reserved_usd: t.dr / 1e6 }; v.total = { spent_usd: t.ts / 1e6, reserved_usd: t.tr / 1e6 };
  v.remaining_today_usd = left(cfg.dayUsd, t.ds + t.dr); v.remaining_total_usd = left(cfg.totalUsd, t.ts + t.tr);
  v.remaining_usd = Math.min(v.remaining_today_usd, v.remaining_total_usd);
  return v;
}

// ---- stores ------------------------------------------------------------------------------------------------
export class MemoryBudgetStore implements BudgetStore {
  rows: BudgetRow[] = [];
  async list() { return this.rows.map((r) => ({ ...r })); }
  async append(row: BudgetRow) { this.rows.push({ ...row }); }
}

// Columns: A time, B token, C kind, D run, E role, F usd, G note. The amount is stored as text with a dot ("0.024000"):
// a number cell is read back formatted in the sheet's locale and "0,024" would not parse.
const RANGE = `'${AGENT_BUDGET_TAB}'!A2:G20000`, MAX_ROWS = 19_900;
export function budgetRowToCells(r: BudgetRow): string[] {
  return [r.time, r.token, r.kind, r.run, r.role, r.usd === null ? "" : r.usd.toFixed(6), String(r.note || "").slice(0, 200)];
}
export function cellsToBudgetRow(c: string[]): BudgetRow | null {
  if (!c || (c[2] !== "reserve" && c[2] !== "settle" && c[2] !== "release")) return null; // the marker row and blank lines
  const usd = c[5] === undefined || String(c[5]).trim() === "" ? null : Number(c[5]);
  return { time: c[0] || "", token: c[1] || "", kind: c[2], run: c[3] || "", role: c[4] || "", usd: usd === null ? null : Number.isFinite(usd) ? usd : NaN, note: c[6] || "" };
}
export class SheetsBudgetStore implements BudgetStore {
  async list(): Promise<BudgetRow[]> {
    if (!sheetsEnabled()) throw new Error("Sheets is not configured");
    let g: string[][] | undefined;
    try { g = (await readRanges(ENGINE_SHEET, [RANGE]))?.[0]; }
    catch (e) { if (String(e).includes("Unable to parse range")) return []; throw e; } // the tab does not exist yet: nothing was ever spent
    if (!g) throw new Error("the budget ledger could not be read");
    // rows past the range read would be invisible and so uncounted: stop before that can happen
    if (g.length >= MAX_ROWS) throw new Error("the budget ledger is full");
    return g.map(cellsToBudgetRow).filter((r): r is BudgetRow => !!r);
  }
  async append(row: BudgetRow) { await appendRow(AGENT_BUDGET_TAB, budgetRowToCells(row)); }
}
