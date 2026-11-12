// Server and tasks (admin panel): reading the server status files, the GitHub Actions runs and the schedules, and
// the rule that marks a workflow "late". Pure functions only; the route (app/api/panel/server/route.ts) does the I/O.
//
// The status files are written on the company server by deploy/ops/serverpanel/collect.py every 2 minutes and served
// by the private data service at /_server/status.json and /_server/history.json. Everything here treats them as
// untrusted input: numbers are checked, strings are cut, arrays are capped.

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown, max = 80): string => (typeof v === "string" ? v.slice(0, max) : "");
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

export type Container = { name: string; state: string; health: string | null; cpu_pct: number | null; mem_mb: number | null; want_running: boolean | null };
export type Runner = { name: string; active: boolean; busy: boolean };
export type ServerStatus = {
  at: string; age_s: number | null;
  host: { uptime_s: number | null; cpus: number | null; load: (number | null)[]; cpu_busy_pct: number | null;
    mem: { total_mb: number | null; used_mb: number | null; available_mb: number | null };
    swap: { total_mb: number | null; used_mb: number | null };
    disk: { total_gb: number | null; used_gb: number | null; free_gb: number | null; used_pct: number | null } | null };
  containers: Container[] | null; runners: Runner[]; models: string[];
  refine: { at: string; websites_checked: number | null; website_check_queue: number | null; needs_ai: number | null; universe: number | null } | null;
  journal: string[] | null;
  /** supplier enrichment job on the server (leads/enrich_server.py): counts and fill rates only */
  enrich: { at: string; state: string; queue: number | null; done: number | null; remaining: number | null; per_hour: number | null; eta_hours: number | null;
    by_tier: Record<string, { done: number | null; total: number | null }>; fill: Record<string, number | null> } | null;
};

/** The status file as the panel may show it, or null when it is not a status file at all. */
export function parseStatus(raw: unknown, now = Date.now()): ServerStatus | null {
  const d = obj(raw);
  if (d.v !== 1 || typeof d.at !== "string" || !d.host) return null;
  const h = obj(d.host), m = obj(h.mem), sw = obj(h.swap), dk = h.disk ? obj(h.disk) : null;
  const at = Date.parse(d.at);
  const cs = d.containers === null || d.containers === undefined ? null : arr(d.containers).slice(0, 40).map((x) => {
    const c = obj(x);
    return { name: str(c.name, 60), state: str(c.state, 20), health: c.health ? str(c.health, 20) : null, cpu_pct: num(c.cpu_pct), mem_mb: num(c.mem_mb),
      want_running: typeof c.want_running === "boolean" ? c.want_running : null };
  }).filter((c) => c.name);
  const rf = d.refine ? obj(d.refine) : null;
  const en = d.enrich ? obj(d.enrich) : null;
  const numMap = (v: unknown, n = 30): Record<string, number | null> => Object.fromEntries(Object.entries(obj(v)).slice(0, n).map(([k, x]) => [k.slice(0, 20), num(x)]));
  return {
    at: d.at.slice(0, 25), age_s: Number.isFinite(at) ? Math.max(0, Math.round((now - at) / 1000)) : null,
    host: { uptime_s: num(h.uptime_s), cpus: num(h.cpus), load: arr(h.load).slice(0, 3).map(num), cpu_busy_pct: num(h.cpu_busy_pct),
      mem: { total_mb: num(m.total_mb), used_mb: num(m.used_mb), available_mb: num(m.available_mb) },
      swap: { total_mb: num(sw.total_mb), used_mb: num(sw.used_mb) },
      disk: dk ? { total_gb: num(dk.total_gb), used_gb: num(dk.used_gb), free_gb: num(dk.free_gb), used_pct: num(dk.used_pct) } : null },
    containers: cs,
    runners: arr(d.runners).slice(0, 10).map((x) => { const r = obj(x); return { name: str(r.name, 8), active: r.active === true, busy: r.busy === true }; }).filter((r) => /^r\d+$/.test(r.name)),
    models: arr(d.models).slice(0, 10).map((x) => str(x, 60)).filter(Boolean),
    refine: rf ? { at: str(rf.at, 25), websites_checked: num(rf.websites_checked), website_check_queue: num(rf.website_check_queue), needs_ai: num(rf.needs_ai), universe: num(rf.universe) } : null,
    journal: d.journal === null || d.journal === undefined ? null : arr(d.journal).slice(-20).map((x) => str(x, 160)),
    enrich: en ? { at: str(en.at, 20), state: str(en.state, 12), queue: num(en.queue), done: num(en.done), remaining: num(en.remaining), per_hour: num(en.per_hour),
      eta_hours: num(en.eta_hours), by_tier: Object.fromEntries(Object.entries(obj(en.by_tier)).slice(0, 6).map(([k, v]) => [k.slice(0, 20), { done: num(obj(v).done), total: num(obj(v).total) }])),
      fill: numMap(en.fill) } : null,
  };
}

export type History = { t: number[]; cpu: (number | null)[]; mem: (number | null)[]; disk: (number | null)[]; wc: (number | null)[]; queue: (number | null)[]; busy_runners: (number | null)[] };
/** The 24-hour history as columns (oldest first), at most 720 points; null when the file is not a history file. */
export function parseHistory(raw: unknown): History | null {
  const d = obj(raw), cols = arr(d.cols).map((c) => str(c, 20));
  if (d.v !== 1 || !cols.length || cols[0] !== "t") return null;
  const col = (k: string) => cols.indexOf(k);
  const pts = arr(d.points).filter((p): p is unknown[] => Array.isArray(p) && p.length === cols.length && num(p[0]) !== null)
    .sort((a, b) => (a[0] as number) - (b[0] as number)).slice(-720);
  const pick = (k: string) => { const i = col(k); return pts.map((p) => (i < 0 ? null : num(p[i]))); };
  return { t: pts.map((p) => (p[0] as number) * 1000), cpu: pick("cpu"), mem: pick("mem"), disk: pick("disk"), wc: pick("wc"), queue: pick("queue"), busy_runners: pick("busy_runners") };
}

/** Websites checked per hour from two snapshots: the newest point and the oldest one at most `windowH` hours before it
 *  whose counter is known. Null when the counter did not move forward or the two are less than 30 minutes apart. */
export function ratePerHour(t: number[], v: (number | null)[], windowH = 6): { per_hour: number; over_h: number } | null {
  let last = -1;
  for (let i = v.length - 1; i >= 0; i--) if (v[i] !== null) { last = i; break; }
  if (last < 0) return null;
  let first = -1;
  for (let i = 0; i < last; i++) if (v[i] !== null && t[last] - t[i] <= windowH * 3600e3) { first = i; break; }
  if (first < 0) return null;
  const hours = (t[last] - t[first]) / 3600e3, d = (v[last] as number) - (v[first] as number);
  if (hours < 0.5 || d < 0) return null;
  return { per_hour: Math.round(d / hours), over_h: Math.round(hours * 10) / 10 };
}

// ---------- schedules ----------

/** Expands one cron field ("*", "*\/n", "a-b", "a,b", "n") over [lo, hi]; null when it cannot be read. */
function field(f: string, lo: number, hi: number): number[] | null {
  const out = new Set<number>();
  for (const part of f.split(",")) {
    const m = part.match(/^(\*|\d+(?:-\d+)?)(?:\/(\d+))?$/);
    if (!m) return null;
    const step = m[2] ? Number(m[2]) : 1;
    let a = lo, b = hi;
    if (m[1] !== "*") { const [x, y] = m[1].split("-").map(Number); a = x; b = y ?? (m[2] ? hi : x); }
    if (a < lo || b > hi || a > b || step < 1) return null;
    for (let i = a; i <= b; i += step) out.add(i);
  }
  return [...out];
}

/** The longest gap in hours between two runs over a week, for one or more 5-field cron lines together.
 *  "@continuous" counts as one hour (the server scheduler restarts it back to back). Day-of-month or month limits
 *  are read as "about monthly" (720 h). Null when no line can be read. */
export function cronIntervalHours(lines: string[]): number | null {
  const times = new Set<number>(); let monthly = false;
  for (const raw of lines) {
    const l = raw.trim();
    if (l === "@continuous") { for (let k = 0; k < 168; k++) times.add(k * 60); continue; }
    const f = l.split(/\s+/);
    if (f.length !== 5) continue;
    const [mi, ho, dom, mon, dow] = [field(f[0], 0, 59), field(f[1], 0, 23), f[2], f[3], field(f[4].replace(/\b7\b/g, "0"), 0, 6)];
    if (!mi || !ho || !dow) continue;
    if (dom !== "*" || mon !== "*") { monthly = true; continue; }
    for (const d of dow) for (const h of ho) for (const m of mi) times.add(d * 1440 + h * 60 + m);
  }
  if (!times.size) return monthly ? 720 : null;
  const s = [...times].sort((a, b) => a - b);
  let gap = s[0] + 10080 - s[s.length - 1];
  for (let i = 1; i < s.length; i++) gap = Math.max(gap, s[i] - s[i - 1]);
  return Math.round((gap / 60) * 100) / 100;
}

/** Workflow file -> its cron lines, from the server scheduler's table (deploy/ops/schedule.tab). */
export function parseScheduleTab(text: string): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const line of String(text || "").split("\n")) {
    const l = line.replace(/#.*/, "").trim();
    if (!l) continue;
    const f = l.split(/\s+/);
    const [cron, wf] = f[0] === "@continuous" ? ["@continuous", f[1]] : [f.slice(0, 5).join(" "), f[5]];
    if (!wf || !/\.ya?ml$/.test(wf)) continue;
    (out[wf] ||= []).push(cron);
  }
  return out;
}

/** The cron lines under "schedule:" of a workflow file (GitHub's own timer). */
export function workflowCrons(yaml: string): string[] {
  return [...String(yaml || "").matchAll(/^\s*-\s*cron:\s*["']([^"']+)["']/gm)].map((m) => m[1].trim());
}

/** The owner's rule: a timed workflow is late when its last run started more than twice its schedule interval ago.
 *  Null when either is unknown (no schedule, or no run seen): unknown is never shown as late or on time. */
export function isLate(lastRunMs: number | null, intervalH: number | null, now = Date.now()): boolean | null {
  if (lastRunMs === null || !Number.isFinite(lastRunMs) || intervalH === null || !(intervalH > 0)) return null;
  return now - lastRunMs > 2 * intervalH * 3600e3;
}

// ---------- GitHub Actions runs ----------

export type GhRun = { name?: string; path?: string; status?: string; conclusion?: string | null; created_at?: string; run_started_at?: string; updated_at?: string; html_url?: string; head_branch?: string };
export type WorkflowRow = { workflow: string; name: string; last_at: string; last_status: string; last_conclusion: string | null; last_duration_s: number | null;
  running: number; queued: number; runs_24h: number; success_24h: number; failure_24h: number; interval_h: number | null; late: boolean | null; url: string };

/** One row per workflow, newest first: last run, its result and duration, and success/failure counts over 24 hours. */
export function groupRuns(runs: GhRun[], schedules: Record<string, string[]>, now = Date.now()): WorkflowRow[] {
  const by = new Map<string, GhRun[]>();
  for (const r of runs) {
    const wf = String(r.path || "").split("/").pop() || String(r.name || "");
    if (!wf) continue;
    (by.get(wf) || by.set(wf, []).get(wf)!).push(r);
  }
  const t = (s?: string) => { const x = Date.parse(String(s || "")); return Number.isFinite(x) ? x : NaN; };
  const rows: WorkflowRow[] = [];
  for (const [wf, list] of by) {
    list.sort((a, b) => t(b.created_at) - t(a.created_at));
    const last = list[0], start = t(last.run_started_at || last.created_at);
    const in24 = list.filter((r) => now - t(r.created_at) <= 864e5);
    const interval = schedules[wf] ? cronIntervalHours(schedules[wf]) : null;
    rows.push({ workflow: wf, name: String(last.name || wf).slice(0, 60), last_at: String(last.run_started_at || last.created_at || ""),
      last_status: String(last.status || ""), last_conclusion: last.conclusion ?? null,
      last_duration_s: last.status === "completed" && Number.isFinite(start) && Number.isFinite(t(last.updated_at)) ? Math.max(0, Math.round((t(last.updated_at) - start) / 1000)) : null,
      running: list.filter((r) => r.status === "in_progress").length, queued: list.filter((r) => r.status === "queued" || r.status === "waiting" || r.status === "pending").length,
      runs_24h: in24.length, success_24h: in24.filter((r) => r.conclusion === "success").length,
      failure_24h: in24.filter((r) => r.conclusion === "failure" || r.conclusion === "timed_out" || r.conclusion === "startup_failure").length,
      interval_h: interval, late: isLate(Number.isFinite(start) ? start : null, interval, now), url: String(last.html_url || "").slice(0, 200) });
  }
  // scheduled workflows with no run in the fetched page: shown, with "last run" unknown
  for (const wf of Object.keys(schedules)) if (!by.has(wf)) rows.push({ workflow: wf, name: wf.replace(/\.ya?ml$/, ""), last_at: "", last_status: "", last_conclusion: null, last_duration_s: null,
    running: 0, queued: 0, runs_24h: 0, success_24h: 0, failure_24h: 0, interval_h: cronIntervalHours(schedules[wf]), late: null, url: "" });
  return rows.sort((a, b) => (b.last_at || "").localeCompare(a.last_at || ""));
}

// ---------- agent budget ----------

// TODO(release/scout): when lib/agentbudget.ts is on main, replace this with its budgetView(), which also applies the
// budget period. Until then this reads the same append-only 'Agent Budget' ledger (A time, B token, C kind, D run,
// E role, F usd, G note): a reservation counts at its settled cost when known, otherwise at the reserved worst case,
// and not at all once released. Days are calendar days in Asia/Jerusalem.
const DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem", year: "numeric", month: "2-digit", day: "2-digit" });
export type AgentBudget = { today_usd: number; total_usd: number; day_cap_usd: number | null; total_cap_usd: number | null; reservations: number; estimated: true };
export function summarizeAgentBudget(rows: string[][], now = Date.now(), caps: { day: number | null; total: number | null } = { day: null, total: null }): AgentBudget {
  const res = new Map<string, { day: string; reserved: number; settled: number | null; released: boolean }>();
  for (const c of rows) if (c && c[2] === "reserve" && c[1] && !res.has(c[1])) {
    const ms = Date.parse(c[0] || ""), usd = Number(c[5]);
    res.set(c[1], { day: Number.isFinite(ms) ? DAY.format(new Date(ms)) : "", reserved: Number.isFinite(usd) && usd > 0 ? usd : 0, settled: null, released: false });
  }
  for (const c of rows) {
    const e = c && res.get(c[1]); if (!e) continue;
    if (c[2] === "release") e.released = true;
    if (c[2] === "settle" && String(c[5] ?? "").trim() !== "" && Number.isFinite(Number(c[5])) && Number(c[5]) >= 0) e.settled = Number(c[5]);
  }
  const today = DAY.format(new Date(now));
  let t = 0, d = 0;
  for (const e of res.values()) { if (e.released) continue; const u = e.settled ?? e.reserved; t += u; if (e.day === today) d += u; }
  const r6 = (x: number) => Math.round(x * 1e6) / 1e6;
  return { today_usd: r6(d), total_usd: r6(t), day_cap_usd: caps.day, total_cap_usd: caps.total, reservations: res.size, estimated: true };
}
