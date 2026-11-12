import { logEvent } from "@/lib/log";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";
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
// web searches, estimated cost, latency); AI_DAILY_BUDGET_USD (default 15) is an alert line shown in the admin panel,
// calls are never refused. Prices are list prices per million tokens, overridable (AI_PRICE_IN, AI_PRICE_OUT, AI_PRICE_SEARCH per
// 1,000 searches); the ledger says "estimated" because the provider's invoice is the only measured figure.
const PRICE = { in: Number(process.env.AI_PRICE_IN || 1), out: Number(process.env.AI_PRICE_OUT || 5), cacheRead: Number(process.env.AI_PRICE_CACHE_READ || 0.1), search: Number(process.env.AI_PRICE_SEARCH || 10) };
const DAILY_BUDGET = Number(process.env.AI_DAILY_BUDGET_USD || 15);
export const estimateCost = (u: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; server_tool_use?: { web_search_requests?: number } }) =>
  ((u.input_tokens || 0) * PRICE.in + (u.output_tokens || 0) * PRICE.out + (u.cache_read_input_tokens || 0) * PRICE.cacheRead) / 1e6 + ((u.server_tool_use?.web_search_requests || 0) * PRICE.search) / 1000;

let spendCache: { day: string; at: number; usd: number } | null = null;
let alertedDay = "";
const todayKey = () => new Date().toISOString().slice(0, 10);
// Today's estimated spend across every instance: the ledger tab, cached 2 minutes, plus what this instance added since.
export async function spentToday(fresh = false): Promise<number> {
  const day = todayKey();
  if (!fresh && spendCache && spendCache.day === day && Date.now() - spendCache.at < 120_000) return spendCache.usd;
  const g = (await readRanges(ENGINE_SHEET, ["'AI Usage'!A1:I5000"]).catch(() => null))?.[0] || [];
  let usd = 0;
  for (const r of g) if (String(r[0] || "").startsWith(day)) usd += Number(r[8]) || 0;
  spendCache = { day, at: Date.now(), usd };
  return usd;
}
export async function budgetState() { const usd = await spentToday(); return { spent_usd: Math.round(usd * 1000) / 1000, alert_usd: DAILY_BUDGET, over_alert: usd >= DAILY_BUDGET, estimated: true }; }

export type CallMeta = { job?: string; ws?: string };
export async function claude(body: Record<string, unknown>, meta: CallMeta = {}): Promise<{ text: string; sources: { url: string; title: string }[] }> {
  const job = meta.job || "unnamed", t0 = Date.now();
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
    if (spendCache && spendCache.day === todayKey()) spendCache.usd += usd;
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

export type Usage = { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; server_tool_use?: { web_search_requests?: number } };
/** True when the price table can be trusted for the configured model: the default model, or prices set explicitly. */
export const pricesKnown = () => !process.env.ANTHROPIC_MODEL || process.env.ANTHROPIC_MODEL === "claude-haiku-5-5" || (!!process.env.AI_PRICE_IN && !!process.env.AI_PRICE_OUT);
// Exactly one request, for callers that reserved the worst-case cost of one request beforehand (lib/pipeline.ts under
// lib/agentbudget.ts). claude() above may make up to three requests (pause_turn, max_tokens continuation), so its
// cost has no bound a reservation could cover. No tools, no continuation: an answer cut at max_tokens is returned as
// it is. usage is null when the provider returned none; the caller then keeps the reservation at the worst case.
export async function claudeOnce(body: { system: string; messages: { role: "user" | "assistant"; content: string }[]; max_tokens: number }, meta: CallMeta = {}): Promise<{ text: string; usage: Usage | null; model: string }> {
  const job = meta.job || "unnamed", t0 = Date.now();
  const log = (u: Usage | null, ok: boolean) => void appendRow("AI Usage", [new Date().toISOString(), job, meta.ws || "", MODEL, u?.input_tokens || 0, u?.output_tokens || 0, u?.cache_read_input_tokens || 0, 0, u ? Math.round(estimateCost(u) * 1e5) / 1e5 : 0, Date.now() - t0, ok ? "ok" : "error"]).catch(() => {});
  let r: Response, j: { usage?: Usage; content?: Block[]; error?: { message?: string; type?: string } };
  try {
    r = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: anthropicHeaders(), body: JSON.stringify({ model: MODEL, system: body.system, messages: body.messages, max_tokens: body.max_tokens }), signal: AbortSignal.timeout(Number(process.env.AI_TIMEOUT_MS || 45000)) });
    j = await r.json().catch(() => ({}));
  } catch (e) { log(null, false); throw e; }
  if (!r.ok) {
    const msg = `Anthropic ${r.status}: ${String(j?.error?.message || j?.error?.type || "").slice(0, 300)}`;
    void logEvent("error", "ai", msg, job); log(null, false);
    throw new Error(msg);
  }
  const usage = j.usage && Number.isFinite(Number(j.usage.input_tokens)) && Number.isFinite(Number(j.usage.output_tokens)) ? j.usage : null;
  log(usage, true);
  return { text: (j.content || []).filter((b) => b.type === "text").map((b) => b.text || "").join("").trim(), usage, model: MODEL };
}
