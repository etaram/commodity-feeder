import { logEvent } from "@/lib/log";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { envCap } from "@/lib/spend";
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

// Today's and this month's estimated spend across every instance, from the ledger tab (A time .. I usd),
// cached 2 minutes, plus what this instance added since. Month and day are UTC, like the ledger's ISO times.
let spendCache: { day: string; month: string; at: number; usd: number; monthUsd: number } | null = null;
let alertedDay = "", refusedLogged = "";
const todayKey = () => new Date().toISOString().slice(0, 10);
async function ledger(fresh = false): Promise<{ usd: number; monthUsd: number } | null> {
  const day = todayKey(), month = day.slice(0, 7);
  if (!fresh && spendCache && spendCache.day === day && Date.now() - spendCache.at < 120_000) return spendCache;
  const g = await readRanges(ENGINE_SHEET, ["'AI Usage'!A1:I100000"]).catch(() => null);
  if (!g) return spendCache && spendCache.month === month ? spendCache : null;   // unreadable: the last known figure, if any
  let usd = 0, monthUsd = 0;
  for (const r of g[0] || []) {
    const ts = String(r?.[0] || "");
    if (!ts.startsWith(month)) continue;
    const v = Number(r[8]) || 0;
    monthUsd += v; if (ts.startsWith(day)) usd += v;
  }
  spendCache = { day, month, at: Date.now(), usd, monthUsd };
  return spendCache;
}
export async function spentToday(fresh = false): Promise<number> { return (await ledger(fresh))?.usd ?? 0; }
/** This calendar month's (UTC) estimated AI spend, or null when the ledger has never been readable on this instance. */
export async function spentThisMonth(fresh = false): Promise<number | null> { return (await ledger(fresh))?.monthUsd ?? null; }
/** Adds a call's estimated cost to this instance's running figures (the ledger row is appended by the caller). */
export function noteSpend(usd: number) {
  if (spendCache && spendCache.day === todayKey() && Number.isFinite(usd) && usd > 0) { spendCache.usd += usd; spendCache.monthUsd += usd; }
}
export const monthlyCap = () => envCap(process.env, "ANTHROPIC_MONTHLY_CAP_USD", 30);
export async function budgetState() {
  const usd = await spentToday(), m = await spentThisMonth(), cap = monthlyCap();
  return { spent_usd: Math.round(usd * 1000) / 1000, alert_usd: DAILY_BUDGET, over_alert: usd >= DAILY_BUDGET, month_usd: m === null ? null : Math.round(m * 1000) / 1000, month_cap_usd: cap, month_stopped: m !== null && m >= cap, estimated: true };
}

// Monthly hard cap (ANTHROPIC_MONTHLY_CAP_USD, default 30): every model call the app makes checks it first and is
// refused, not sent, once this month's estimated spend has reached the cap. The self-check's 5-token ping (job
// "health") is exempt so the daily screen check keeps telling whether the key works; it is still metered and counted.
// If the ledger has never been readable on this instance the call goes through (and is metered); a later read applies the cap.
export const CAP_REFUSAL = "The monthly AI budget is used up";
export function capMessage(spent: number, cap: number) {
  return `${CAP_REFUSAL} (about $${spent.toFixed(2)} of $${cap.toFixed(2)} this month, ANTHROPIC_MONTHLY_CAP_USD). AI answers are paused until the 1st of next month (UTC) or until the owner raises the cap.`;
}
export async function checkMonthlyCap(job: string): Promise<void> {
  if (job === "health") return;
  const cap = monthlyCap(), m = await spentThisMonth();
  if (m === null || m < cap) return;
  const key = todayKey() + job;
  if (refusedLogged !== key) { refusedLogged = key; void logEvent("warn", "ai", "AI call refused: monthly cap reached", `job ${job}; $${m.toFixed(2)} of $${cap}`); }
  throw new Error(capMessage(m, cap));
}

export type CallMeta = { job?: string; ws?: string };
export async function claude(body: Record<string, unknown>, meta: CallMeta = {}): Promise<{ text: string; sources: { url: string; title: string }[] }> {
  const job = meta.job || "unnamed", t0 = Date.now();
  await checkMonthlyCap(job);
  // the budget is an alert, never a refusal: calls always go through; crossing it is logged once a day per instance
  if (DAILY_BUDGET > 0 && alertedDay !== todayKey() && (await spentToday()) >= DAILY_BUDGET) {
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
  const record = (ok: boolean) => {
    const usd = estimateCost(usage);
    noteSpend(usd);
    void appendRow("AI Usage", [new Date().toISOString(), job, meta.ws || "", MODEL, usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens, usage.server_tool_use.web_search_requests, Math.round(usd * 1e5) / 1e5, Date.now() - t0, ok ? "ok" : "error"]).catch(() => {});
  };
  for (let turn = 0; turn < 3; turn++) {
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: anthropicHeaders(),
      body: JSON.stringify({ model: MODEL, ...body, messages }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = `Anthropic ${r.status}: ${String(j?.error?.message || j?.error?.type || "").slice(0, 300)}`;
      void logEvent("error", "ai", msg, job);
      record(false);
      throw new Error(msg);
    }
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
