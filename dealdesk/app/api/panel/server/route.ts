import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { PUBLIC_FALLBACK, RAW_ROOT } from "@/lib/rawbase";
import { ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { type GhRun, groupRuns, parseHistory, parseScheduleTab, parseStatus, ratePerHour, summarizeAgentBudget, workflowCrons } from "@/lib/serverstatus";

// Server and tasks (admin panel, refreshed every 60 s while the tab is open): the company server's status and 24-hour
// history (written by deploy/ops/serverpanel/collect.py, served by the private data service at /_server/), the GitHub
// Actions runs of the last 24 hours by workflow, the processing counters and queues, the agent budget and the server
// scheduler's freshness check. Every part fails on its own and says so; nothing is estimated except the AI cost.
export const dynamic = "force-dynamic";
export const maxDuration = 30;

const REPO = "etaram/commodity-feeder";
const safe = async <T,>(p: Promise<T>, ms = 8000): Promise<T | { error: string }> =>
  Promise.race([p.catch((e) => ({ error: String(e).slice(0, 160) })), new Promise<{ error: string }>((r) => setTimeout(() => r({ error: "timed out" }), ms))]);
const getJson = async (path: string): Promise<unknown | null> => {
  const r = await fetch(`${RAW_ROOT}/${path}`, { cache: "no-store", signal: AbortSignal.timeout(6000) });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
};
const getText = async (path: string): Promise<string | null> => {
  const r = await fetch(`${RAW_ROOT}/${path}`, { cache: "no-store", signal: AbortSignal.timeout(6000) });
  return r.ok ? r.text() : null;
};

// GitHub Actions runs of the public repository, without a token (60 requests an hour per address). Cached 120 s per
// server instance; a conditional request (ETag) that answers 304 does not count against that limit. On a refusal the
// last good copy is returned with a note.
type RunsCache = { at: number; etag: string; runs: GhRun[]; total: number };
let runsCache: RunsCache | null = null;
async function ghRuns(): Promise<{ runs: GhRun[]; total: number; fetched_at: string; cached: boolean; note: string }> {
  const now = Date.now();
  const out = (c: RunsCache, cached: boolean, note = "") => ({ runs: c.runs, total: c.total, fetched_at: new Date(c.at).toISOString(), cached, note });
  if (runsCache && now - runsCache.at < 120_000) return out(runsCache, true);
  const h: Record<string, string> = { Accept: "application/vnd.github+json", "User-Agent": "sinder-deal-desk" };
  if (runsCache?.etag) h["If-None-Match"] = runsCache.etag;
  let r: Response;
  try { r = await fetch(`https://api.github.com/repos/${REPO}/actions/runs?per_page=100`, { headers: h, cache: "no-store", signal: AbortSignal.timeout(8000) }); }
  catch (e) { if (runsCache) return out(runsCache, true, `GitHub did not answer; showing the copy from ${new Date(runsCache.at).toISOString().slice(11, 16)} UTC`); throw e; }
  if (r.status === 304 && runsCache) { runsCache.at = now; return out(runsCache, false); }
  if (!r.ok) {
    const why = r.status === 403 || r.status === 429 ? "GitHub rate limit reached" : `GitHub answered ${r.status}`;
    if (runsCache) return out(runsCache, true, `${why}; showing the copy from ${new Date(runsCache.at).toISOString().slice(11, 16)} UTC`);
    throw new Error(why);
  }
  const j = await r.json() as { total_count?: number; workflow_runs?: GhRun[] };
  const keep = (x: GhRun): GhRun => ({ name: x.name, path: x.path, status: x.status, conclusion: x.conclusion, created_at: x.created_at, run_started_at: x.run_started_at, updated_at: x.updated_at, html_url: x.html_url, head_branch: x.head_branch });
  runsCache = { at: now, etag: r.headers.get("etag") || "", runs: (j.workflow_runs || []).map(keep), total: Number(j.total_count) || 0 };
  return out(runsCache, false);
}

// Schedules: the server scheduler's table when it is on main (deploy/ops/schedule.tab), otherwise the "schedule:"
// crons of each workflow file. Cached one hour.
let schedCache: { at: number; key: string; v: Record<string, string[]>; source: string } | null = null;
async function schedules(workflows: string[]): Promise<{ v: Record<string, string[]>; source: string }> {
  const key = [...workflows].sort().join(",");
  if (schedCache && schedCache.key === key && Date.now() - schedCache.at < 3600e3) return schedCache;
  const tab = await getText("deploy/ops/schedule.tab").catch(() => null);
  const v: Record<string, string[]> = tab ? parseScheduleTab(tab) : {};
  await Promise.all(workflows.filter((wf) => !v[wf] && /^[\w.-]+\.ya?ml$/.test(wf)).map(async (wf) => {
    const crons = workflowCrons((await getText(`.github/workflows/${wf}`).catch(() => null)) || "");
    if (crons.length) v[wf] = crons;
  }));
  schedCache = { at: Date.now(), key, v, source: tab ? "schedule.tab + workflow files" : "workflow files" };
  return schedCache;
}

const envNum = (k: string, d: number) => { const x = Number(process.env[k]); return process.env[k] && Number.isFinite(x) ? x : d; };

export async function GET() {
  const { s, res } = await gate("admin");
  if (!s) return res;
  const now = Date.now();
  const [server, gh, refine, budget, sched] = await Promise.all([
    // in preview and staging there is no data service: say so instead of showing zeros
    PUBLIC_FALLBACK ? Promise.resolve({ available: false as const, reason: "no data service in this environment (DATA_BASE_URL is not set)" })
      : safe((async () => {
        const [st, hi] = await Promise.all([getJson("_server/status.json"), getJson("_server/history.json").catch(() => null)]);
        const status = parseStatus(st, now);
        if (!status) return { available: false as const, reason: st === null ? "the server has not published its status yet" : "the status file could not be read" };
        const history = parseHistory(hi);
        return { available: true as const, status, history, website_rate: history ? ratePerHour(history.t, history.wc) : null };
      })()),
    safe((async () => {
      const g = await ghRuns();
      const wfs = [...new Set(g.runs.map((r) => String(r.path || "").split("/").pop() || "").filter(Boolean))];
      const sc = await schedules(wfs).catch(() => ({ v: {}, source: "unavailable" }));
      const oldest = g.runs.reduce((m, r) => Math.min(m, Date.parse(String(r.created_at)) || m), now);
      return { workflows: groupRuns(g.runs, sc.v, now), fetched_at: g.fetched_at, cached: g.cached, note: g.note, runs_in_page: g.runs.length, total_runs: g.total,
        covers_h: Math.round((now - oldest) / 3600e3 * 10) / 10, schedule_source: sc.source };
    })(), 15000),
    // counts only, the same file the admin panel's refinement section reads
    safe(getJson("data/leads/refine_progress.json").then((d) => {
      if (!d || typeof d !== "object") return null;
      const x = d as Record<string, unknown>, n = (k: string) => (typeof x[k] === "number" ? x[k] as number : null);
      return { at: String(x.at || ""), universe: n("universe"), processed: n("processed"), completed: n("completed"), websites_checked: n("websites_checked"), website_check_queue: n("website_check_queue"), needs_ai: n("needs_ai") };
    })),
    // the agents' spend cap ledger, when the tab exists (release/scout); otherwise null
    safe(readRanges(ENGINE_SHEET, ["'Agent Budget'!A2:G20000"]).then((g) => (g ? summarizeAgentBudget(g[0] || [], now, { day: envNum("AGENT_BUDGET_DAY_USD", 1), total: envNum("AGENT_BUDGET_TOTAL_USD", 5) }) : null))
      .catch((e) => { if (String(e).includes("Unable to parse range")) return null; throw e; })),
    // the server scheduler's freshness check (release/scheduler), when it publishes one
    PUBLIC_FALLBACK ? Promise.resolve(null) : safe(getJson("_status/freshness.json")),
  ]);
  return NextResponse.json({ ok: true, at: new Date(now).toISOString(), server, actions: gh, refine, agent_budget: budget, schedule: sched });
}
