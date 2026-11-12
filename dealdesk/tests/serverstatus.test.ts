// Server and tasks (lib/serverstatus.ts): the status file parser, the history, the website-check rate, the cron
// interval and the owner's "late" rule (last run older than twice the schedule interval).
import { cronIntervalHours, groupRuns, isLate, parseHistory, parseScheduleTab, parseStatus, ratePerHour, summarizeAgentBudget, workflowCrons } from "@/lib/serverstatus";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const H = 3600e3, NOW = Date.parse("2026-11-12T12:00:00Z");

// ---- status parser ----
const raw = {
  v: 1, at: "2026-11-12T11:58:00Z",
  host: { uptime_s: 86400, cpus: 4, load: [1.2, 0.9, "x"], cpu_busy_pct: 23.4, cpu_window_s: 120, mem: { total_mb: 15000, used_mb: 6000, available_mb: 9000 }, swap: { total_mb: 0, used_mb: 0 },
    disk: { total_gb: 160, used_gb: 70, free_gb: 90, used_pct: 43.8 } },
  containers: [{ name: "sinder-data-1", state: "running", health: null, cpu_pct: 0.1, mem_mb: 12, want_running: true }, { name: "", state: "running" }, { name: "x".repeat(200), state: "exited", want_running: "yes" }],
  runners: [{ name: "r1", active: true, busy: true }, { name: "r2", active: true, busy: false }, { name: "/home/runner/r3", active: true, busy: false }],
  models: ["ollama-bench"], refine: { at: "2026-11-12T10:34Z", websites_checked: 18167, website_check_queue: 309818, needs_ai: 8420, universe: 1043458 },
  journal: ["a", 5, "b".repeat(500)],
};
const st = parseStatus(raw, NOW)!;
ok(!!st, "a status file is read");
ok(st.age_s === 120, "its age is measured from 'at'");
ok(st.host.cpus === 4 && st.host.cpu_busy_pct === 23.4 && st.host.mem.used_mb === 6000 && st.host.disk?.used_pct === 43.8, "host numbers are kept");
ok(st.host.load[2] === null, "a load value that is not a number becomes null, never 0");
ok(st.containers!.length === 2 && st.containers![1].name.length === 60 && st.containers![1].want_running === null, "containers without a name are dropped, long names are cut, odd flags become null");
ok(st.runners.map((r) => r.name).join() === "r1,r2", "only runner numbers (r1, r2...) are kept, never a path");
ok(st.journal!.length === 3 && st.journal![1] === "" && st.journal![2].length === 160, "journal lines are text, cut to 160 characters");
ok(parseStatus({ ...raw, v: 2 }) === null && parseStatus(null) === null && parseStatus("x") === null && parseStatus({ v: 1, at: "t" }) === null, "anything that is not a version-1 status file is refused");
ok(parseStatus({ ...raw, containers: null })!.containers === null, "no docker answer stays 'unknown' (null), not an empty list");
ok(parseStatus({ ...raw, journal: undefined })!.journal === null, "no journal on the server stays null");

// ---- history and the website-check rate ----
const t0 = (NOW - 6 * H) / 1000;
const hist = parseHistory({ v: 1, step_s: 120, cols: ["t", "cpu", "mem", "disk", "load1", "wc", "queue", "busy_runners"],
  points: [[t0 + 3 * 3600, 30, 40, 44, 1, 1300, 900, 1], [t0, 10, 40, 44, 1, 1000, 1000, 0], ["bad"], [t0 + 6 * 3600, 50, 41, 44, 2, 1600, 800, 2]] })!;
ok(hist.t.length === 3 && hist.t[0] === t0 * 1000 && hist.cpu.join() === "10,30,50", "history points are sorted oldest first and broken ones are dropped");
ok(parseHistory({ v: 1, cols: ["x"], points: [] }) === null, "a file without a time column is not a history");
const rate = ratePerHour(hist.t, hist.wc)!;
ok(rate.per_hour === 100 && rate.over_h === 6, "websites per hour from the first and last snapshot: 600 in 6 hours = 100 per hour");
ok(ratePerHour([NOW - 600e3, NOW], [5, 10]) === null, "two snapshots less than 30 minutes apart give no rate");
ok(ratePerHour([NOW - 2 * H, NOW], [10, 5]) === null, "a counter that went backwards gives no rate");
ok(ratePerHour([NOW - 30 * H, NOW], [1, 9]) === null, "a snapshot older than the window is not used");

// ---- cron intervals ----
ok(cronIntervalHours(["35 * * * *"]) === 1, "hourly cron: 1 hour");
ok(cronIntervalHours(["10 */2 * * *", "40 4,16 * * *"]) === 2, "every two hours plus two extra runs: the longest gap is 2 hours");
ok(cronIntervalHours(["40 1 * * *", "40 13 * * *"]) === 12, "two daily lines 12 hours apart: 12 hours");
ok(cronIntervalHours(["17 3 * * 1"]) === 168, "weekly: 168 hours");
ok(cronIntervalHours(["@continuous"]) === 1, "back-to-back (server scheduler): 1 hour");
ok(cronIntervalHours(["0 0 1 * *"]) === 720, "a day-of-month limit is read as about monthly");
ok(cronIntervalHours(["nonsense"]) === null && cronIntervalHours([]) === null, "unreadable or no schedule: unknown");
ok(cronIntervalHours(["7,37 * * * *"]) === 0.5, "twice an hour: 30 minutes");

// ---- the late rule ----
ok(isLate(NOW - 2.5 * H, 1, NOW) === true, "hourly workflow last run 2.5 hours ago: late");
ok(isLate(NOW - 1.9 * H, 1, NOW) === false, "hourly workflow last run 1.9 hours ago: on time");
ok(isLate(NOW - 2 * H, 1, NOW) === false, "exactly twice the interval is not yet late");
ok(isLate(null, 1, NOW) === null && isLate(NOW, null, NOW) === null && isLate(NOW, 0, NOW) === null, "unknown last run or schedule: neither late nor on time");

// ---- schedules from the scheduler's table and from workflow files ----
const tab = parseScheduleTab("# comment\n35 * * * * panel.yml 3 -\n@continuous company-check.yml 4 -\n10 */2 * * * leads.yml 6 only=light\n40 4,16 * * * leads.yml 6 only=heavy\n\n");
ok(tab["panel.yml"].join() === "35 * * * *" && tab["company-check.yml"].join() === "@continuous" && tab["leads.yml"].length === 2, "schedule.tab: one entry per workflow, every line kept");
ok(workflowCrons("on:\n  schedule:\n    - cron: '35 * * * *'\n    - cron: \"0 5 * * *\"\n  workflow_dispatch:\n").join("|") === "35 * * * *|0 5 * * *", "crons are read from a workflow file");

// ---- runs grouped by workflow ----
const iso = (ms: number) => new Date(ms).toISOString();
const runs = [
  { name: "panel", path: ".github/workflows/panel.yml", status: "completed", conclusion: "success", created_at: iso(NOW - 3 * H), run_started_at: iso(NOW - 3 * H), updated_at: iso(NOW - 3 * H + 90e3) },
  { name: "panel", path: ".github/workflows/panel.yml", status: "completed", conclusion: "failure", created_at: iso(NOW - 4 * H), run_started_at: iso(NOW - 4 * H), updated_at: iso(NOW - 4 * H + 60e3) },
  { name: "panel", path: ".github/workflows/panel.yml", status: "completed", conclusion: "success", created_at: iso(NOW - 30 * H), run_started_at: iso(NOW - 30 * H), updated_at: iso(NOW - 30 * H + 60e3) },
  { name: "leads", path: ".github/workflows/leads.yml", status: "in_progress", conclusion: null, created_at: iso(NOW - 1 * H), run_started_at: iso(NOW - 1 * H), updated_at: iso(NOW) },
];
const rows = groupRuns(runs, { "panel.yml": ["35 * * * *"], "leads.yml": ["10 */2 * * *"], "trends.yml": ["17 3 * * 1"] }, NOW);
const p = rows.find((r) => r.workflow === "panel.yml")!, l = rows.find((r) => r.workflow === "leads.yml")!, tr = rows.find((r) => r.workflow === "trends.yml")!;
ok(rows[0].workflow === "leads.yml", "the most recently started workflow comes first");
ok(p.last_conclusion === "success" && p.last_duration_s === 90 && p.runs_24h === 2 && p.success_24h === 1 && p.failure_24h === 1, "panel: last result, duration and 24-hour counts (the 30-hour-old run is not counted)");
ok(p.interval_h === 1 && p.late === true, "panel is hourly and last started 3 hours ago: late");
ok(l.running === 1 && l.last_duration_s === null && l.late === false, "a running workflow has no duration yet and is not late");
ok(tr.last_at === "" && tr.late === null && tr.interval_h === 168, "a scheduled workflow with no run in the page is listed with an unknown last run");

// ---- agent budget ledger ----
const day = "2026-11-12T08:00:00Z", yday = "2026-11-11T08:00:00Z";
const b = summarizeAgentBudget([
  [day, "a", "reserve", "run1", "scout", "0.300000", ""], [day, "a", "settle", "run1", "scout", "0.120000", ""],
  [day, "b", "reserve", "run1", "scout", "0.200000", ""],
  [day, "c", "reserve", "run1", "scout", "0.500000", ""], [day, "c", "release", "run1", "scout", "", "lost the race"],
  [yday, "d", "reserve", "run0", "scout", "0.400000", ""], [yday, "d", "settle", "run0", "scout", "", "unknown"],
  ["marker"],
], NOW, { day: 1, total: 5 });
ok(Math.abs(b.today_usd - 0.32) < 1e-9, "today: a settled call at its cost (0.12), an open reservation at its worst case (0.20), a released one not at all");
ok(Math.abs(b.total_usd - 0.72) < 1e-9, "total adds yesterday's call settled as unknown at its worst case (0.40)");
ok(b.reservations === 4 && b.day_cap_usd === 1 && b.estimated === true, "reservations counted once; caps and the 'estimated' mark are passed on");

process.exit(fail ? 1 : 0);
