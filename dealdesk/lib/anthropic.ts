import { logEvent } from "@/lib/log";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { defaultCap, envCap } from "@/lib/spend";
// Shared Anthropic API client for the web app. Cheapest model by default (Claude Haiku 5.5).
export const MODEL = process.env.ANTHROPIC_MODEL || "claude-haiku-5-5";

type Block = { type: string; text?: string; citations?: { url?: string; title?: string }[] };

// Request headers shared by every Anthropic call in the app. A key that is not scoped to a workspace must name the
// workspace in a header (ANTHROPIC_WORKSPACE_ID), otherwise the API refuses the request.
export function anthropicHeaders(): Record<string, string> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error("AI is not configured (ANTHROPIC_API_KEY)");
  return { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
    ...(process.env.ANTHROPIC_WORKSPACE_ID ? { "anthropic-workspace-id": process.env.ANTHROPIC_WORKSPACE_ID } : {}) };
}

// Cost discipline (spec section 14): every call is metered into the hidden 'AI Usage' tab (job, workspace, tokens,
// web searches, estimated cost, latency); AI_DAILY_BUDGET_USD (default 15) is an alert line shown in the admin panel;
// the monthly cap below (ANTHROPIC_MONTHLY_CAP_USD) is the hard limit that refuses calls. Prices are list prices per million tokens, overridable (AI_PRICE_IN, AI_PRICE_OUT, AI_PRICE_SEARCH per
// 1,000 searches); the ledger says "estimated" because the provider's invoice is the only measured figure.
const PRICE = { in: Number(process.env.AI_PRICE_IN || 1), out: Number(process.env.AI_PRICE_OUT || 5), cacheRead: Number(process.env.AI_PRICE_CACHE_READ || 0.1), search: Number(process.env.AI_PRICE_SEARCH || 10) };
const DAILY_BUDGET = Number(process.env.AI_DAILY_BUDGET_USD || 15);
export const estimateCost = (u: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; server_tool_use?: { web_search_requests?: number } }) =>
  ((u.input_tokens || 0) * PRICE.in + (u.output_tokens || 0) * PRICE.out + (u.cache_read_input_tokens || 0) * PRICE.cacheRead) / 1e6 + ((u.server_tool_use?.web_search_requests || 0) * PRICE.search) / 1000;

// ---- Monthly hard cap (ANTHROPIC_MONTHLY_CAP_USD, default 30) ---------------------------------------------------
// Every model call the app makes goes through reserveCall() first, per turn (claude(), the deal agent, the Telegram
// assistant, continuation and tool turns alike). No job is exempt, the health ping included (it is opt-in, aiping=1).
//   spent     this month's estimated spend from the 'AI Usage' ledger (all instances), plus the actual cost of this
//             instance's calls that the last ledger read cannot contain yet (row not yet appended when the read began,
//             or an append that failed: those stay counted in memory for the rest of the month)
//   reserved  the worst-case cost of every call this instance has in flight (in-process, shared by all callers)
//   worst     this call's worst case: estimated input tokens (characters / 2, generous) + max_tokens at list price,
//             plus the web searches it may run and the result text they add
// A call is refused, before anything is sent, when spent + reserved + worst > cap. On completion the reservation is
// replaced by the actual cost; on an error it is released. Fail closed: when this month's spend cannot be read the
// call is refused; a good reading is reused for at most LAST_GOOD_MS when a later read fails, never treated as 0.
const FRESH_MS = 60_000, LAST_GOOD_MS = 5 * 60_000, READ_TIMEOUT_MS = 10_000;
const SEARCH_RESULT_TOKENS = 10_000, DEFAULT_SEARCHES = 5, DEFAULT_MAX_TOKENS = 4096;
let spendCache: { day: string; month: string; readAt: number; usd: number; monthUsd: number } | null = null;
let reading: Promise<boolean> | null = null;
let alertedDay = "", refusedLogged = "";
const todayKey = () => new Date().toISOString().slice(0, 10);
type Held = { usd: number; job: string; at: number };
type Unseen = { usd: number; day: string; month: string; doneAt: number | null };   // doneAt: when its ledger row landed
const holds = new Map<number, Held>();
const unseen = new Map<number, Unseen>();
let seq = 0;

/** Worst-case cost in USD of one Messages API request body, at the same list prices as estimateCost. */
export function worstCaseCost(body: Record<string, unknown>): number {
  const text = JSON.stringify([body.system ?? "", body.messages ?? [], body.tools ?? []]);
  const inTok = Math.ceil(text.length / 2);
  const out = Number(body.max_tokens) > 0 ? Number(body.max_tokens) : DEFAULT_MAX_TOKENS;
  let searches = 0;
  for (const t of (Array.isArray(body.tools) ? body.tools : []) as { type?: string; max_uses?: number }[])
    if (String(t?.type || "").startsWith("web_search")) searches += Number(t.max_uses) > 0 ? Number(t.max_uses) : DEFAULT_SEARCHES;
  // with server-side search the request is sampled again after each search, each time with the results added
  const input = (searches + 1) * (inTok + searches * SEARCH_RESULT_TOKENS);
  return estimateCost({ input_tokens: input, output_tokens: out, server_tool_use: { web_search_requests: searches } });
}
/** The worst case of every call this instance has in flight. */
export const reservedNow = () => { let s = 0; for (const h of holds.values()) s += h.usd; return s; };

function readLedger(): Promise<boolean> {
  return (reading ||= (async () => {
    const readAt = Date.now(), day = todayKey(), month = day.slice(0, 7);
    let timer: ReturnType<typeof setTimeout> | undefined;
    const g = await Promise.race([
      readRanges(ENGINE_SHEET, ["'AI Usage'!A1:I100000"], { timeoutMs: READ_TIMEOUT_MS }),
      new Promise<null>((r) => { timer = setTimeout(() => r(null), READ_TIMEOUT_MS + 2000); }),
    ]).catch(() => null).finally(() => clearTimeout(timer));
    if (!g) return false;   // not configured, failed or too slow: unknown, never 0
    let usd = 0, monthUsd = 0;
    for (const r of g[0] || []) {
      const ts = String(r?.[0] || "");
      if (!ts.startsWith(month)) continue;
      const v = Number(r[8]);
      if (!Number.isFinite(v) || v < 0) continue;
      monthUsd += v; if (ts.startsWith(day)) usd += v;
    }
    spendCache = { day, month, readAt, usd, monthUsd };
    // rows that had landed before this read began are in it now
    for (const [k, e] of unseen) if ((e.doneAt !== null && e.doneAt <= readAt) || e.month !== month) unseen.delete(k);
    return true;
  })().finally(() => { reading = null; }));
}
// Today's and this month's estimated spend: the last ledger reading (re-read after FRESH_MS) plus this instance's
// actual costs the reading cannot contain yet. null = unknown (no reading, or the last good one is older than LAST_GOOD_MS).
async function ledger(fresh = false): Promise<{ usd: number; monthUsd: number } | null> {
  const day = todayKey(), month = day.slice(0, 7);
  const usable = () => spendCache && spendCache.month === month;
  if (fresh || !usable() || spendCache!.day !== day || Date.now() - spendCache!.readAt >= FRESH_MS) {
    const ok = await readLedger();
    if (!ok && !(usable() && Date.now() - spendCache!.readAt < LAST_GOOD_MS)) return null;
    if (!usable()) return null;
  }
  const c = spendCache!;
  let usd = c.day === day ? c.usd : 0, monthUsd = c.monthUsd;
  for (const e of unseen.values()) {
    if (e.month !== month || (e.doneAt !== null && e.doneAt <= c.readAt)) continue;
    monthUsd += e.usd; if (e.day === day) usd += e.usd;
  }
  return { usd, monthUsd };
}
export async function spentToday(fresh = false): Promise<number | null> { return (await ledger(fresh))?.usd ?? null; }
/** This calendar month's (UTC) estimated AI spend, or null when it cannot be read right now (the cap then refuses). */
export async function spentThisMonth(fresh = false): Promise<number | null> { return (await ledger(fresh))?.monthUsd ?? null; }
// default by month (UTC): the setup month November 2026 is USD 50 (owner decision 12 Nov 2026 20:35), then USD 30;
// ANTHROPIC_MONTHLY_CAP_USD, when set, overrides the default for every month
export { defaultCap };
export const monthlyCap = () => envCap(process.env, "ANTHROPIC_MONTHLY_CAP_USD", defaultCap());
const r3 = (x: number) => Math.round(x * 1000) / 1000;
export async function budgetState() {
  const usd = await spentToday(), m = await spentThisMonth(), cap = monthlyCap(), held = reservedNow();
  return { spent_usd: usd === null ? null : r3(usd), alert_usd: DAILY_BUDGET, over_alert: usd !== null && usd >= DAILY_BUDGET, month_usd: m === null ? null : r3(m),
    month_reserved_usd: r3(held), month_inflight: holds.size, month_cap_usd: cap, month_unknown: m === null, month_stopped: m === null || m + held >= cap, estimated: true };
}

export const CAP_REFUSAL = "The monthly AI budget is used up";
export const CAP_UNKNOWN = "AI is paused: this month's AI spend cannot be read";
export function capMessage(spent: number, cap: number, reserved = 0, worst = 0) {
  if (spent + reserved < cap) return `${CAP_REFUSAL} for a call this size: it could cost up to $${worst.toFixed(2)} and only $${Math.max(0, cap - spent - reserved).toFixed(2)} of the $${cap.toFixed(2)} monthly cap is free (about $${spent.toFixed(2)} spent, $${reserved.toFixed(2)} held for calls in progress; ANTHROPIC_MONTHLY_CAP_USD). Smaller AI answers can still run.`;
  return `${CAP_REFUSAL} (about $${spent.toFixed(2)} of $${cap.toFixed(2)} this month${reserved > 0 ? `, plus $${reserved.toFixed(2)} held for calls in progress` : ""}, ANTHROPIC_MONTHLY_CAP_USD). AI answers are paused until the 1st of next month (UTC) or until the owner raises the cap.`;
}
export const unknownMessage = () => `${CAP_UNKNOWN} (the usage ledger did not answer), so the monthly cap cannot be checked and the call was not sent. It resumes by itself once the ledger answers again.`;
function refuse(job: string, what: string, detail: string, msg: string): never {
  const key = todayKey() + job + what;
  if (refusedLogged !== key) { refusedLogged = key; void logEvent("warn", "ai", `AI call refused: ${what}`, `job ${job}; ${detail}`); }
  throw new Error(msg);
}

export type Hold = { id: number; usd: number; settle: (usage: Parameters<typeof estimateCost>[0]) => { usd: number; entry: number }; release: () => void; uncertain: () => void };
/** Reserves the worst-case cost of one model request, or throws the refusal. Settle with the actual usage, or release. */
export async function reserveCall(job: string, body: Record<string, unknown>): Promise<Hold> {
  const worst = worstCaseCost(body), cap = monthlyCap();
  const l = await ledger();
  if (!l) refuse(job, "spend unknown", "the AI Usage ledger could not be read", unknownMessage());
  // no await between this check and the reservation: parallel callers each see the others' reservations
  const held = reservedNow();
  if (l.monthUsd + held + worst > cap) refuse(job, "monthly cap", `$${l.monthUsd.toFixed(2)} spent + $${held.toFixed(2)} held + $${worst.toFixed(3)} this call > $${cap}`, capMessage(l.monthUsd, cap, held, worst));
  const id = ++seq;
  holds.set(id, { usd: worst, job, at: Date.now() });
  let done = false;
  return {
    id, usd: worst,
    settle(usage) {
      const usd = estimateCost(usage || {});
      if (done) return { usd, entry: 0 };
      done = true; holds.delete(id);
      const day = todayKey(), entry = ++seq;
      if (Number.isFinite(usd) && usd > 0) unseen.set(entry, { usd, day, month: day.slice(0, 7), doneAt: null });
      return { usd, entry };
    },
    release() { done = true; holds.delete(id); },
    // the request may have reached the provider (network error, timeout, unreadable answer): it may have been billed.
    // The worst case stays counted for the rest of the month, since a missing usage row does not prove zero charge.
    uncertain() {
      if (done) return;
      done = true; holds.delete(id);
      const day = todayKey();
      unseen.set(++seq, { usd: worst, day, month: day.slice(0, 7), doneAt: null });
    },
  };
}
/** The ledger row holding these settled costs has been appended (or failed: then they stay counted in memory). */
export function ledgered(entries: number[], append: Promise<unknown>) {
  return append.then(() => { const t = Date.now(); for (const k of entries) { const e = unseen.get(k); if (e) e.doneAt = t; } }, () => {});
}
/** Kept for callers that only check: refuses when this month's spend is unknown or already at the cap. */
export async function checkMonthlyCap(job: string): Promise<void> {
  const h = await reserveCall(job, { max_tokens: 1, messages: [] });
  h.release();
}

/** One model request through the cap: reserve, send, settle (with its 'AI Usage' row) or release. */
export async function modelTurn(job: string, ws: string, body: Record<string, unknown>): Promise<{ ok: boolean; status: number; j: Record<string, any>; usd: number }> {
  const hold = await reserveCall(job, body), t1 = Date.now();
  let res: Response, j: Record<string, any>;
  try {
    res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: anthropicHeaders(), body: JSON.stringify(body) });
    j = await res.json().catch(() => ({}));
  } catch (e) { hold.uncertain(); throw e; }
  if (!res.ok) { hold.release(); return { ok: false, status: res.status, j, usd: 0 }; }
  const u = j.usage || {}, s = hold.settle(u);
  void ledgered([s.entry], appendRow("AI Usage", [new Date().toISOString(), job, ws, String(body.model || MODEL), u.input_tokens || 0, u.output_tokens || 0, u.cache_read_input_tokens || 0, u.server_tool_use?.web_search_requests || 0, Math.round(s.usd * 1e5) / 1e5, Date.now() - t1, "ok"]));
  return { ok: true, status: res.status, j, usd: s.usd };
}

export type CallMeta = { job?: string; ws?: string };
export async function claude(body: Record<string, unknown>, meta: CallMeta = {}): Promise<{ text: string; sources: { url: string; title: string }[] }> {
  const job = meta.job || "unnamed", t0 = Date.now();
  // the daily budget is an alert line only; the monthly cap (reserveCall, every turn below) is the refusal
  if (DAILY_BUDGET > 0 && alertedDay !== todayKey() && ((await spentToday()) ?? 0) >= DAILY_BUDGET) {
    alertedDay = todayKey();
    void logEvent("warn", "ai", `daily AI spend passed the alert line (${DAILY_BUDGET} USD)`, `job ${job}; calls continue`);
  }
  let messages = body.messages as unknown[];
  const out: Block[] = [];
  const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, server_tool_use: { web_search_requests: 0 } };
  const meter = (u: Record<string, unknown> | undefined) => {
    if (!u) return;
    usage.input_tokens += Number(u.input_tokens) || 0; usage.output_tokens += Number(u.output_tokens) || 0; usage.cache_read_input_tokens += Number(u.cache_read_input_tokens) || 0;
    usage.server_tool_use.web_search_requests += Number((u.server_tool_use as { web_search_requests?: number } | undefined)?.web_search_requests) || 0;
  };
  const settled: number[] = [];
  const record = (ok: boolean) => {
    const usd = estimateCost(usage);
    void ledgered(settled, appendRow("AI Usage", [new Date().toISOString(), job, meta.ws || "", MODEL, usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens, usage.server_tool_use.web_search_requests, Math.round(usd * 1e5) / 1e5, Date.now() - t0, ok ? "ok" : "error"]));
  };
  for (let turn = 0; turn < 3; turn++) {
    const req = { model: MODEL, ...body, messages };
    let hold: Hold;
    try { hold = await reserveCall(job, req); }      // every turn, continuations included
    catch (e) { if (turn) record(false); throw e; }
    let r: Response, j: Record<string, any>;
    try {
      r = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: anthropicHeaders(), body: JSON.stringify(req) });
      j = await r.json().catch(() => ({}));
    } catch (e) { hold.uncertain(); record(false); throw e; }
    if (!r.ok) {
      hold.release();
      const msg = `Anthropic ${r.status}: ${String(j?.error?.message || j?.error?.type || "").slice(0, 300)}`;
      void logEvent("error", "ai", msg, job);
      record(false);
      throw new Error(msg);
    }
    settled.push(hold.settle(j.usage || {}).entry);
    meter(j.usage);
    out.push(...((j.content || []) as Block[]));
    if (j.stop_reason === "pause_turn") { messages = [...messages, { role: "assistant", content: j.content }]; continue; }
    if (j.stop_reason === "max_tokens") {
      // Ran out of room: ask once more to finish from where it stopped, so answers never end mid-sentence.
      messages = [...messages, { role: "assistant", content: j.content }, { role: "user", content: "Continue exactly where you stopped and finish the answer briefly. Do not repeat anything." }];
      continue;
    }
    break;
  }
  record(true);
  const text = out.filter((b) => b.type === "text").map((b) => b.text || "").join("").trim();
  const seen = new Set<string>(), sources: { url: string; title: string }[] = [];
  for (const b of out) for (const c of b.citations || []) if (c.url && !seen.has(c.url)) { seen.add(c.url); sources.push({ url: c.url, title: c.title || c.url }); }
  return { text, sources };
}
