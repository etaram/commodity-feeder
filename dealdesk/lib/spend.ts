// Spending this month (admin panel, "Spending this month"): per service, what was spent since the 1st of the month
// (UTC) against that service's monthly cap, and the total against a total cap, in plain words. Pure functions only;
// the route (app/api/panel/spend) reads the ledgers and the configuration and passes them in.
//
// Services and where each number comes from:
//   Anthropic API      the system's own 'AI Usage' ledger (every model call, list-price estimate)        cap ANTHROPIC_MONTHLY_CAP_USD (30)
//   Agents (ledger)    the 'Agent Budget' ledger of the agent roles, when that tab exists                 cap AGENT_BUDGET_TOTAL_USD (5)
//   Search API         not connected: 0 queries (the paid search lane is off)                              cap SEARCH_MONTHLY_CAP_USD (0)
//   WhatsApp           not connected: 0                                                                    cap WHATSAPP_MONTHLY_CAP_USD (0)
//   Fixed costs        server, domain, mailbox, phone number: from SPEND_FIXED_COSTS (JSON) or lib/fixedcosts.json;
//                      an amount the owner has not confirmed stays "to confirm" and is not added to the total
// Total cap: SPEND_MONTHLY_CAP_USD (60). A cap that is set but unreadable counts as 0: a typo must not open the tap.

export type Level = "within" | "near" | "stopped" | "off" | "unknown";
export type ServiceLine = { id: string; name: string; spent_usd: number | null; cap_usd: number | null; level: Level; words: string; basis: string; detail?: string; estimated?: boolean; reserved_usd?: number };
export type FixedCost = { id: string; name: string; monthly_usd: number | null; status: "confirmed" | "to confirm"; note?: string };
export type SpendReport = { month: string; at: string; services: ServiceLine[]; fixed: FixedCost[]; total: { spent_usd: number; cap_usd: number; level: Level; words: string; unconfirmed: string[] }; note: string };

export const NEAR = 0.8;

/** A cap from the environment: unset or empty = the default; set but not a number >= 0 = 0 (refuse). */
export function envCap(env: Record<string, string | undefined>, k: string, d: number): number {
  const v = env[k];
  if (v === undefined || v.trim() === "") return d;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

/** Default Anthropic monthly cap: USD 50 in November 2026 (setup month, owner's decision), USD 30 from December. */
export const defaultCap = (now: number | Date = new Date()) => (new Date(now).toISOString().slice(0, 7) === "2026-11" ? 50 : 30);

export const monthKey = (t: number | Date = Date.now()) => new Date(t).toISOString().slice(0, 7);

/** Estimated USD of the 'AI Usage' rows (A time ISO, B job, ..., I usd) in the given month; also calls and by-job totals. */
export function aiMonth(rows: string[][], month: string): { usd: number; calls: number; byJob: Record<string, number> } {
  let usd = 0, calls = 0;
  const byJob: Record<string, number> = {};
  for (const r of rows || []) {
    if (!r || !String(r[0] || "").startsWith(month)) continue;
    const u = Number(r[8]);
    if (!Number.isFinite(u) || u < 0) continue;
    usd += u; calls++;
    const j = String(r[1] || "unnamed");
    byJob[j] = (byJob[j] || 0) + u;
  }
  return { usd: Math.round(usd * 1e6) / 1e6, calls, byJob };
}

/** The agents' 'Agent Budget' ledger (A time, B token, C kind, D run, E role, F usd): what this month's reservations
 *  count for (released 0, settled = actual, otherwise the reserved worst case), the same rule as lib/agentbudget. */
export function agentMonth(rows: string[][], month: string): { usd: number; reservations: number } {
  const res = new Map<string, { month: string; reserved: number; settled: number | null; released: boolean }>();
  for (const c of rows || []) if (c && c[2] === "reserve" && c[1] && !res.has(c[1])) {
    const usd = Number(c[5]);
    res.set(c[1], { month: String(c[0] || "").slice(0, 7), reserved: Number.isFinite(usd) && usd > 0 ? usd : 0, settled: null, released: false });
  }
  for (const c of rows || []) {
    const e = c && res.get(c[1]); if (!e) continue;
    if (c[2] === "release") e.released = true;
    if (c[2] === "settle" && String(c[5] ?? "").trim() !== "" && Number.isFinite(Number(c[5])) && Number(c[5]) >= 0) e.settled = Number(c[5]);
  }
  let usd = 0, n = 0;
  for (const e of res.values()) { if (e.month !== month) continue; n++; if (!e.released) usd += e.settled ?? e.reserved; }
  return { usd: Math.round(usd * 1e6) / 1e6, reservations: n };
}

/** Fixed monthly costs from configuration: a JSON array; anything unreadable becomes "to confirm", never a guessed price. */
export function parseFixed(raw: unknown): FixedCost[] {
  let v: unknown = raw;
  if (typeof raw === "string") { try { v = JSON.parse(raw); } catch { return []; } }
  if (!Array.isArray(v)) return [];
  const out: FixedCost[] = [];
  for (const x of v as Record<string, unknown>[]) {
    if (!x || typeof x !== "object" || !x.name) continue;
    const n = x.monthly_usd === null || x.monthly_usd === undefined || x.monthly_usd === "" ? null : Number(x.monthly_usd);
    const amount = n !== null && Number.isFinite(n) && n >= 0 ? n : null;
    const confirmed = amount !== null && x.status === "confirmed";
    out.push({ id: String(x.id || x.name).slice(0, 40), name: String(x.name).slice(0, 80), monthly_usd: amount, status: confirmed ? "confirmed" : "to confirm", note: x.note ? String(x.note).slice(0, 160) : undefined });
  }
  return out;
}

/** Plain words for spent against cap. cap 0 with nothing spent = "off". */
export function levelOf(spent: number | null, cap: number | null, refuses = true): { level: Level; words: string } {
  if (spent === null) return { level: "unknown", words: "not known right now" };
  if (cap === null) return { level: "unknown", words: "no cap set" };
  if (cap === 0) return spent > 0 ? { level: "stopped", words: "stopped: the cap is 0" } : { level: "off", words: "off (not connected, nothing spent)" };
  if (spent >= cap) return { level: "stopped", words: refuses ? "stopped at the cap" : "over the cap" };
  if (spent >= cap * NEAR) return { level: "near", words: "near the cap" };
  return { level: "within", words: "within budget" };
}

export type SpendInputs = {
  now: number; env: Record<string, string | undefined>;
  ai: { rows: string[][] } | { error: string };
  agent: { rows: string[][] } | { error: string } | null;   // null = the ledger tab does not exist
  fixed: FixedCost[];
  aiReserved?: number;   // worst case of the AI calls in flight on this instance (lib/anthropic.ts reservedNow)
};
const r2 = (x: number) => Math.round(x * 100) / 100;

export function spendReport(i: SpendInputs): SpendReport {
  const month = monthKey(i.now), env = i.env;
  const services: ServiceLine[] = [];
  // Anthropic
  const aiCap = envCap(env, "ANTHROPIC_MONTHLY_CAP_USD", defaultCap(i.now));   // same default as the enforcement (lib/anthropic.ts)
  if ("error" in i.ai) services.push({ id: "anthropic", name: "Anthropic API (AI)", spent_usd: null, cap_usd: aiCap, ...levelOf(null, aiCap), basis: "the system's usage log could not be read", detail: i.ai.error });
  else {
    const a = aiMonth(i.ai.rows, month);
    const top = Object.entries(a.byJob).sort((x, y) => y[1] - x[1]).slice(0, 4).map(([j, u]) => `${j} $${r2(u).toFixed(2)}`).join(", ");
    const held = i.aiReserved && i.aiReserved > 0 ? i.aiReserved : 0;
    // the level is what the cap check sees: spent plus the worst case of the calls in flight
    services.push({ id: "anthropic", name: "Anthropic API (AI)", spent_usd: r2(a.usd), cap_usd: aiCap, ...levelOf(a.usd + held, aiCap), estimated: true, reserved_usd: Math.round(held * 1000) / 1000,
      basis: `${a.calls} calls this month, from the system's own usage log at list prices (an estimate; the invoice is the measured figure). Each call reserves its worst case first and is refused before it is sent when spent + reserved would pass the cap; if the log cannot be read, AI calls are refused`,
      detail: [held > 0 ? `$${held.toFixed(3)} reserved for calls in progress` : "", top ? `largest: ${top}` : ""].filter(Boolean).join("; ") || undefined });
  }
  // agents' budget ledger
  const agCap = envCap(env, "AGENT_BUDGET_TOTAL_USD", 5);
  if (i.agent === null) services.push({ id: "agents", name: "Agents (budget ledger)", spent_usd: 0, cap_usd: agCap, level: "off", words: "not running (no ledger yet)", basis: "the agents' budget ledger does not exist yet" });
  else if ("error" in i.agent) services.push({ id: "agents", name: "Agents (budget ledger)", spent_usd: null, cap_usd: agCap, ...levelOf(null, agCap), basis: "the agents' budget ledger could not be read", detail: i.agent.error });
  else {
    const g = agentMonth(i.agent.rows, month);
    services.push({ id: "agents", name: "Agents (budget ledger)", spent_usd: r2(g.usd), cap_usd: agCap, ...levelOf(g.usd, agCap), estimated: true,
      basis: `${g.reservations} model calls reserved this month; open reservations count at their worst case. Each call is refused before it is made when the cap would be passed` });
  }
  // search API and WhatsApp: not connected, no paid call path exists
  const sCap = envCap(env, "SEARCH_MONTHLY_CAP_USD", 0);
  services.push({ id: "search", name: "Search API", spent_usd: 0, cap_usd: sCap, ...levelOf(0, sCap), basis: "no paid search service is connected; company enrichment uses free public sources only" });
  const wCap = envCap(env, "WHATSAPP_MONTHLY_CAP_USD", 0);
  services.push({ id: "whatsapp", name: "WhatsApp", spent_usd: 0, cap_usd: wCap, ...levelOf(0, wCap), basis: "not connected yet" });
  // total
  const fixedKnown = i.fixed.filter((f) => f.status === "confirmed" && f.monthly_usd !== null);
  const variable = services.reduce((a, s) => a + (s.spent_usd || 0), 0);
  const spent = r2(variable + fixedKnown.reduce((a, f) => a + (f.monthly_usd || 0), 0));
  const cap = envCap(env, "SPEND_MONTHLY_CAP_USD", 60);
  const unknown = services.filter((s) => s.spent_usd === null).map((s) => s.name);
  const lv = levelOf(spent, cap, false);
  const unconfirmed = i.fixed.filter((f) => f.status !== "confirmed").map((f) => f.name);
  return { month, at: new Date(i.now).toISOString(), services, fixed: i.fixed,
    total: { spent_usd: spent, cap_usd: cap, level: unknown.length && lv.level === "within" ? "unknown" : lv.level, words: unknown.length ? `${lv.words}, but ${unknown.join(" and ")} could not be read` : lv.words, unconfirmed },
    note: "Month = calendar month in UTC. AI amounts are list-price estimates from the system's own logs. Fixed costs marked \"to confirm\" are not added to the total until the owner confirms the amount." };
}
