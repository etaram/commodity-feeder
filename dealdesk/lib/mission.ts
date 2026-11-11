// The durable mission object: one goal, worked by specialist roles as idempotent tasks with dependencies, a cost
// budget and an independent review. Pure state logic over an injected append-only store: no model calls, no sending,
// no UI. Every function rebuilds the state from the store first, so a restart (new process, same store) continues
// where the last one stopped and never duplicates a task. Single writer per mission is assumed (as in the outbox).
import { createHash } from "crypto";
import { TEAM } from "./team";

export const MISSION_TYPES = ["win_tender", "supply_winner", "client_bd", "strategic_signal"] as const;
export type MissionType = (typeof MISSION_TYPES)[number];

export const MISSION_ROLES = ["source_evidence", "tender_project", "osint", "commercial_strategy", "technical_sourcing",
  "regional_relations", "logistics_compliance", "finance", "negotiation_comms", "red_team"] as const;
export type MissionRole = (typeof MISSION_ROLES)[number];

export type MissionStatus = "queued" | "running" | "waiting_on_external" | "needs_owner" | "paused_on_risk" | "completed" | "failed" | "cancelled";
export type TaskStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type ReviewResult = { reviewer_role: MissionRole; verdict: "pass" | "fail"; notes: string; at: string };

export type MissionTask = {
  idempotency_key: string; role: MissionRole; question: string; depends_on: string[];
  attempt: number; max_attempts: number; cost_reservation_usd: number;
  status: TaskStatus; output: unknown; reviewer_result: ReviewResult | null;
  last_error: string; seq: number; // seq: creation order inside the mission
};

export type Mission = {
  id: string; workspace: string; type: MissionType; goal: string; represented_org: string; deal_id: string;
  cost_budget_usd: number; spent_usd: number; allowed_tools: string[]; stop_rules: string[];
  status: MissionStatus; next_decision: string; tasks: MissionTask[];
  created_at: string; updated_at: string;
};

// Personas (lib/team.ts member ids) behind each role. Six regional personas share regional_relations. Arjun plans both
// commercial strategy and negotiation. osint and red_team are internal: no outward persona signs their work, and
// red_team is deliberately not Omar (evidence), so the reviewer is never the persona whose work is under review.
export const ROLE_PERSONAS: Record<MissionRole, string[]> = {
  source_evidence: ["evidence"],
  tender_project: ["analyst"],
  osint: [],
  commercial_strategy: ["negotiation"],
  technical_sourcing: ["sourcing"],
  regional_relations: ["relations_asia", "relations_south_asia", "relations_latam", "relations_africa", "relations_europe", "relations_mena"],
  logistics_compliance: ["logistics"],
  finance: ["economics"],
  negotiation_comms: ["negotiation"],
  red_team: [],
};
export const personasFor = (role: MissionRole) => ROLE_PERSONAS[role].map((id) => TEAM.find((m) => m.id === id)!).filter(Boolean);
export const roleOfPersona = (memberId: string): MissionRole | null => MISSION_ROLES.find((r) => ROLE_PERSONAS[r].includes(memberId)) || null;

/** Who reviews a role's work: red_team; red_team's own work is reviewed by source_evidence. Never the same role. */
export const reviewerFor = (role: MissionRole): MissionRole => (role === "red_team" ? "source_evidence" : "red_team");

// ---- storage ----------------------------------------------------------------------------------------------
// Append-only rows; the highest rev per (workspace, mission_id, kind, id) wins. Task rows carry the task, the mission
// row carries everything except tasks.
export type MissionRow = { workspace: string; mission_id: string; kind: "mission" | "task"; id: string; rev: number; time: string; data: Record<string, unknown> };
export interface MissionStore {
  load(workspace: string, missionId: string): Promise<MissionRow[]>;
  append(row: MissionRow): Promise<void>;
}
export class MemoryMissionStore implements MissionStore {
  rows: MissionRow[] = [];
  async load(workspace: string, missionId: string) { return this.rows.filter((r) => r.workspace === workspace && r.mission_id === missionId).map((r) => JSON.parse(JSON.stringify(r)) as MissionRow); }
  async append(row: MissionRow) { this.rows.push(JSON.parse(JSON.stringify(row))); }
}
export type Ctx = { store: MissionStore; now: () => number };

export type Res<T = {}> = ({ ok: true; mission: Mission } & T) | { ok: false; error: string; mission: Mission | null };

const sha = (v: string) => createHash("sha256").update(v).digest("hex");
const iso = (ctx: Ctx) => new Date(ctx.now()).toISOString();
const money = (v: unknown) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.round(v * 1e6) / 1e6 : NaN);
const TERMINAL: MissionStatus[] = ["completed", "failed", "cancelled"];
const isRole = (r: unknown): r is MissionRole => MISSION_ROLES.includes(r as MissionRole);

type Loaded = { mission: Mission; revs: Map<string, number> };

/** Rebuild a mission from its rows. Returns null when the mission does not exist. */
export function rebuild(rows: MissionRow[]): Mission | null { return fold(rows)?.mission || null; }

function fold(rows: MissionRow[]): Loaded | null {
  const best = new Map<string, MissionRow>();
  for (const r of rows) { const k = `${r.kind}:${r.id}`, cur = best.get(k); if (!cur || r.rev >= cur.rev) best.set(k, r); }
  const head = [...best.values()].find((r) => r.kind === "mission");
  if (!head) return null;
  const tasks = [...best.values()].filter((r) => r.kind === "task").map((r) => r.data as unknown as MissionTask).sort((a, b) => a.seq - b.seq);
  const revs = new Map<string, number>();
  for (const [k, r] of best) revs.set(k, r.rev);
  return { mission: { ...(head.data as unknown as Omit<Mission, "tasks">), tasks }, revs };
}

export async function loadMission(ctx: Ctx, workspace: string, id: string): Promise<Mission | null> {
  return rebuild(await ctx.store.load(workspace, id));
}

async function open(ctx: Ctx, workspace: string, id: string): Promise<Loaded | null> { return fold(await ctx.store.load(workspace, id)); }

async function persist(ctx: Ctx, l: Loaded, changedTasks: MissionTask[] = [], head = true): Promise<void> {
  const m = l.mission, time = iso(ctx);
  for (const t of changedTasks) {
    const k = `task:${t.idempotency_key}`, rev = (l.revs.get(k) || 0) + 1;
    await ctx.store.append({ workspace: m.workspace, mission_id: m.id, kind: "task", id: t.idempotency_key, rev, time, data: t as unknown as Record<string, unknown> });
    l.revs.set(k, rev);
  }
  if (head) {
    m.updated_at = time;
    const { tasks: _tasks, ...rest } = m;
    const k = `mission:${m.id}`, rev = (l.revs.get(k) || 0) + 1;
    await ctx.store.append({ workspace: m.workspace, mission_id: m.id, kind: "mission", id: m.id, rev, time, data: rest as unknown as Record<string, unknown> });
    l.revs.set(k, rev);
  }
}

// Money held by tasks that are running now.
export const reservedUsd = (m: Mission) => m.tasks.filter((t) => t.status === "running").reduce((s, t) => s + t.cost_reservation_usd, 0);
export const remainingUsd = (m: Mission) => Math.max(0, m.cost_budget_usd - m.spent_usd - reservedUsd(m));
export const toolAllowed = (m: Mission, tool: string) => m.allowed_tools.includes(tool);
const taskOf = (m: Mission, key: string) => m.tasks.find((t) => t.idempotency_key === key) || null;
const reviewed = (t: MissionTask) => t.status === "completed" && t.reviewer_result?.verdict === "pass";

export type MissionInput = { id?: string; workspace: string; type: MissionType; goal: string; represented_org: string; deal_id?: string; cost_budget_usd: number; allowed_tools?: string[]; stop_rules?: string[] };

/** Create a mission. The id is derived from the input when not given, so the same request never makes a second mission. */
export async function createMission(ctx: Ctx, input: MissionInput): Promise<Res<{ created: boolean }>> {
  const bad = (error: string): Res<{ created: boolean }> => ({ ok: false, error, mission: null });
  if (!input.workspace) return bad("workspace is required");
  if (!MISSION_TYPES.includes(input.type)) return bad(`unknown mission type: ${String(input.type)}`);
  if (!String(input.goal || "").trim()) return bad("goal is required");
  if (!String(input.represented_org || "").trim()) return bad("represented_org is required");
  const budget = money(input.cost_budget_usd);
  if (Number.isNaN(budget)) return bad("cost_budget_usd must be a number, 0 or more");
  const id = input.id || `MIS-${sha(`${input.workspace}|${input.type}|${input.deal_id || ""}|${input.goal.trim()}`).slice(0, 12)}`;
  const existing = await open(ctx, input.workspace, id);
  if (existing) return { ok: true, mission: existing.mission, created: false };
  const time = iso(ctx);
  const mission: Mission = {
    id, workspace: input.workspace, type: input.type, goal: input.goal.trim(), represented_org: input.represented_org.trim(), deal_id: input.deal_id || "",
    cost_budget_usd: budget, spent_usd: 0, allowed_tools: [...(input.allowed_tools || [])], stop_rules: [...(input.stop_rules || [])],
    status: "queued", next_decision: "", tasks: [], created_at: time, updated_at: time,
  };
  await persist(ctx, { mission, revs: new Map() });
  return { ok: true, mission, created: true };
}

export type TaskInput = { idempotency_key: string; role: MissionRole; question: string; depends_on?: string[]; max_attempts?: number; cost_reservation_usd?: number };

/** Add a task. The same idempotency key never creates a second task: the existing one is returned unchanged. */
export async function addTask(ctx: Ctx, workspace: string, missionId: string, input: TaskInput): Promise<Res<{ task: MissionTask; created: boolean }>> {
  const l = await open(ctx, workspace, missionId);
  if (!l) return { ok: false, error: "mission not found", mission: null };
  const m = l.mission, bad = (error: string): Res<{ task: MissionTask; created: boolean }> => ({ ok: false, error, mission: m });
  const key = String(input.idempotency_key || "").trim();
  if (!key) return bad("idempotency_key is required");
  const have = taskOf(m, key);
  if (have) return { ok: true, mission: m, task: have, created: false };
  if (TERMINAL.includes(m.status)) return bad(`mission is ${m.status}`);
  if (!isRole(input.role)) return bad(`unknown role: ${String(input.role)}`);
  if (!String(input.question || "").trim()) return bad("question is required");
  const deps = [...new Set(input.depends_on || [])];
  // A dependency must already exist, so the graph can never contain a cycle.
  for (const d of deps) if (!taskOf(m, d)) return bad(`depends_on names an unknown task: ${d}`);
  const max = input.max_attempts ?? 3, cost = money(input.cost_reservation_usd ?? 0);
  if (!(Number.isInteger(max) && max >= 1)) return bad("max_attempts must be a whole number, 1 or more");
  if (Number.isNaN(cost)) return bad("cost_reservation_usd must be a number, 0 or more");
  const task: MissionTask = { idempotency_key: key, role: input.role, question: input.question.trim(), depends_on: deps, attempt: 0, max_attempts: max,
    cost_reservation_usd: cost, status: "queued", output: null, reviewer_result: null, last_error: "", seq: m.tasks.length };
  m.tasks.push(task);
  await persist(ctx, l, [task], false);
  return { ok: true, mission: m, task, created: true };
}

/** Tasks that may start now: queued, every dependency completed and passed review, mission queued or running. */
export function nextRunnable(m: Mission): MissionTask[] {
  if (m.status !== "queued" && m.status !== "running") return [];
  return m.tasks.filter((t) => t.status === "queued" && t.depends_on.every((d) => { const x = taskOf(m, d); return !!x && reviewed(x); }));
}

/** Tasks whose work is done and waits for an independent review. */
export const awaitingReview = (m: Mission) => m.tasks.filter((t) => t.status === "completed" && !t.reviewer_result);

/**
 * Reserve the task's cost and start it (attempt + 1). Refuses when spent + running reservations + this one would
 * exceed the budget, and then sets the mission to needs_owner. Calling it again for a task that is already running
 * (after a restart) changes nothing.
 */
export async function reserveCost(ctx: Ctx, workspace: string, missionId: string, key: string): Promise<Res<{ task: MissionTask; reserved_usd: number; already: boolean }>> {
  const l = await open(ctx, workspace, missionId);
  if (!l) return { ok: false, error: "mission not found", mission: null };
  const m = l.mission, bad = (error: string): Res<{ task: MissionTask; reserved_usd: number; already: boolean }> => ({ ok: false, error, mission: m });
  const t = taskOf(m, key);
  if (!t) return bad("task not found");
  if (t.status === "running") return { ok: true, mission: m, task: t, reserved_usd: t.cost_reservation_usd, already: true };
  if (!nextRunnable(m).includes(t)) return bad(m.status !== "queued" && m.status !== "running" ? `mission is ${m.status}` : t.status !== "queued" ? `task is ${t.status}` : "dependencies are not completed and reviewed");
  const need = m.spent_usd + reservedUsd(m) + t.cost_reservation_usd;
  if (need > m.cost_budget_usd + 1e-9) {
    m.status = "needs_owner";
    m.next_decision = `budget: task ${t.idempotency_key} needs ${t.cost_reservation_usd} USD, ${remainingUsd(m)} USD of ${m.cost_budget_usd} USD is left. Raise the budget or cancel.`;
    await persist(ctx, l);
    return bad("budget would be exceeded");
  }
  t.status = "running"; t.attempt += 1; t.last_error = "";
  m.status = "running"; m.next_decision = "";
  await persist(ctx, l, [t]);
  return { ok: true, mission: m, task: t, reserved_usd: t.cost_reservation_usd, already: false };
}

/** Record a running task's output and its real cost (default: the reservation). It then waits for review. */
export async function completeTask(ctx: Ctx, workspace: string, missionId: string, key: string, output: unknown, actualCostUsd?: number): Promise<Res<{ task: MissionTask; already: boolean }>> {
  const l = await open(ctx, workspace, missionId);
  if (!l) return { ok: false, error: "mission not found", mission: null };
  const m = l.mission, t = taskOf(m, key);
  if (!t) return { ok: false, error: "task not found", mission: m };
  if (t.status === "completed") return { ok: true, mission: m, task: t, already: true };
  if (t.status !== "running") return { ok: false, error: `task is ${t.status}, not running`, mission: m };
  const cost = actualCostUsd === undefined ? t.cost_reservation_usd : money(actualCostUsd);
  if (Number.isNaN(cost)) return { ok: false, error: "actual cost must be a number, 0 or more", mission: m };
  t.status = "completed"; t.output = output ?? null; t.reviewer_result = null;
  m.spent_usd = money(m.spent_usd + cost);
  if (m.status === "running") m.next_decision = `review: ${t.idempotency_key} waits for ${reviewerFor(t.role)}`;
  await persist(ctx, l, [t]);
  return { ok: true, mission: m, task: t, already: false };
}

function retryOrFail(m: Mission, t: MissionTask, error: string) {
  t.last_error = String(error || "failed").slice(0, 500);
  if (t.attempt < t.max_attempts) { t.status = "queued"; return; }
  t.status = "failed";
  if (!TERMINAL.includes(m.status)) { m.status = "failed"; m.next_decision = `task ${t.idempotency_key} failed after ${t.attempt} attempt(s): ${t.last_error}`; }
}

/** A running task failed: it goes back to queued until max_attempts is used up, then it is failed and so is the mission. */
export async function failTask(ctx: Ctx, workspace: string, missionId: string, key: string, error: string, actualCostUsd = 0): Promise<Res<{ task: MissionTask; will_retry: boolean }>> {
  const l = await open(ctx, workspace, missionId);
  if (!l) return { ok: false, error: "mission not found", mission: null };
  const m = l.mission, t = taskOf(m, key);
  if (!t) return { ok: false, error: "task not found", mission: m };
  if (t.status !== "running") return { ok: false, error: `task is ${t.status}, not running`, mission: m };
  const cost = money(actualCostUsd);
  if (Number.isNaN(cost)) return { ok: false, error: "actual cost must be a number, 0 or more", mission: m };
  m.spent_usd = money(m.spent_usd + cost);
  retryOrFail(m, t, error);
  await persist(ctx, l, [t]);
  return { ok: true, mission: m, task: t, will_retry: (t.status as TaskStatus) === "queued" };
}

/**
 * Independent review of a completed task. A role never reviews its own work: red_team reviews, and red_team's own
 * tasks are reviewed by source_evidence. A failed review sends the task back for another attempt (or fails it).
 * The mission completes when every task is completed and passed review.
 */
export async function reviewTask(ctx: Ctx, workspace: string, missionId: string, key: string, review: { reviewer_role: MissionRole; verdict: "pass" | "fail"; notes?: string }): Promise<Res<{ task: MissionTask }>> {
  const l = await open(ctx, workspace, missionId);
  if (!l) return { ok: false, error: "mission not found", mission: null };
  const m = l.mission, t = taskOf(m, key), bad = (error: string): Res<{ task: MissionTask }> => ({ ok: false, error, mission: m });
  if (!t) return bad("task not found");
  if (!isRole(review.reviewer_role)) return bad(`unknown reviewer role: ${String(review.reviewer_role)}`);
  if (review.reviewer_role === t.role) return bad(`a task produced by ${t.role} cannot be reviewed by the same role`);
  if (review.reviewer_role !== reviewerFor(t.role)) return bad(`${t.role} work is reviewed by ${reviewerFor(t.role)}`);
  if (review.verdict !== "pass" && review.verdict !== "fail") return bad("verdict must be pass or fail");
  if (t.status !== "completed") return bad(`task is ${t.status}, not completed`);
  if (t.reviewer_result) return bad("task is already reviewed");
  const result: ReviewResult = { reviewer_role: review.reviewer_role, verdict: review.verdict, notes: String(review.notes || "").slice(0, 2000), at: iso(ctx) };
  t.reviewer_result = result;
  if (review.verdict === "fail") retryOrFail(m, t, `review failed: ${result.notes || "no notes"}`);
  else if (m.status === "running") {
    if (m.tasks.every(reviewed)) { m.status = "completed"; m.next_decision = ""; }
    else { const w = awaitingReview(m)[0]; m.next_decision = w ? `review: ${w.idempotency_key} waits for ${reviewerFor(w.role)}` : ""; }
  }
  await persist(ctx, l, [t]);
  return { ok: true, mission: m, task: t };
}

async function setStatus(ctx: Ctx, workspace: string, missionId: string, fn: (m: Mission) => string | MissionTask[]): Promise<Res> {
  const l = await open(ctx, workspace, missionId);
  if (!l) return { ok: false, error: "mission not found", mission: null };
  const r = fn(l.mission);
  if (typeof r === "string") return { ok: false, error: r, mission: l.mission };
  await persist(ctx, l, r);
  return { ok: true, mission: l.mission };
}

/** Pause on a risk (a stop rule, a red flag, the owner's word). Running tasks may still report; nothing new starts. */
export const pause = (ctx: Ctx, workspace: string, missionId: string, reason: string) => setStatus(ctx, workspace, missionId, (m) => {
  if (TERMINAL.includes(m.status)) return `mission is ${m.status}`;
  m.status = "paused_on_risk"; m.next_decision = `paused: ${String(reason || "risk").slice(0, 300)}`; return [];
});

/** The mission waits for something outside (a reply, a document). Nothing new starts until resume. */
export const waitOnExternal = (ctx: Ctx, workspace: string, missionId: string, what: string) => setStatus(ctx, workspace, missionId, (m) => {
  if (m.status !== "queued" && m.status !== "running") return `mission is ${m.status}`;
  m.status = "waiting_on_external"; m.next_decision = `waiting: ${String(what || "external event").slice(0, 300)}`; return [];
});

/** The mission needs the owner: a precise question nobody else can answer. Nothing new starts until resume. */
export const needOwner = (ctx: Ctx, workspace: string, missionId: string, question: string) => setStatus(ctx, workspace, missionId, (m) => {
  if (TERMINAL.includes(m.status)) return `mission is ${m.status}`;
  if (m.status === "paused_on_risk") return "mission is paused_on_risk"; // a risk pause is never replaced by a question
  m.status = "needs_owner"; m.next_decision = `owner: ${String(question || "decision needed").slice(0, 900)}`; return [];
});

/** Continue after a pause, a wait or an owner decision. A budget stop comes straight back unless the budget was raised. */
export const resume = (ctx: Ctx, workspace: string, missionId: string) => setStatus(ctx, workspace, missionId, (m) => {
  if (m.status !== "paused_on_risk" && m.status !== "needs_owner" && m.status !== "waiting_on_external") return `mission is ${m.status}`;
  m.status = m.tasks.some((t) => t.attempt > 0) ? "running" : "queued"; m.next_decision = "";
  if (m.tasks.length && m.tasks.every(reviewed)) m.status = "completed";
  return [];
});

/** The owner's budget decision. Only raises or lowers the ceiling; it does not resume. */
export const setBudget = (ctx: Ctx, workspace: string, missionId: string, budgetUsd: number) => setStatus(ctx, workspace, missionId, (m) => {
  const b = money(budgetUsd);
  if (Number.isNaN(b)) return "budget must be a number, 0 or more";
  if (TERMINAL.includes(m.status)) return `mission is ${m.status}`;
  m.cost_budget_usd = b; return [];
});

/** Cancel: final. Queued and running tasks are cancelled; money already spent stays recorded. */
export const cancel = (ctx: Ctx, workspace: string, missionId: string, reason = "cancelled") => setStatus(ctx, workspace, missionId, (m) => {
  if (m.status === "cancelled") return [];
  if (m.status === "completed") return "mission is completed";
  const changed = m.tasks.filter((t) => t.status === "queued" || t.status === "running");
  for (const t of changed) t.status = "cancelled";
  m.status = "cancelled"; m.next_decision = String(reason).slice(0, 300); return changed;
});
