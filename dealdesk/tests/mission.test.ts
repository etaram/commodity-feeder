// Durable mission object (lib/mission.ts) against the in-memory store. No model calls, nothing is sent.
import { addTask, awaitingReview, cancel, completeTask, createMission, failTask, loadMission, MemoryMissionStore, MISSION_ROLES, nextRunnable, pause, personasFor, remainingUsd, reserveCost, reservedUsd, resume, reviewerFor, reviewTask, ROLE_PERSONAS, roleOfPersona, setBudget, toolAllowed, waitOnExternal, type Ctx } from "@/lib/mission";
import { TEAM } from "@/lib/team";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const WS = "sinder";

function world() {
  const store = new MemoryMissionStore();
  const clock = { t: Date.parse("2026-11-11T08:00:00Z") };
  const ctx: Ctx = { store, now: () => (clock.t += 1000) };
  return { store, ctx };
}
const INPUT = { workspace: WS, type: "win_tender" as const, goal: "Win fixture tender T-1 for industrial pumps", represented_org: "Example Org", deal_id: "D-1", cost_budget_usd: 10, allowed_tools: ["search_tenders", "search_suppliers"], stop_rules: ["sanctions hit"] };
const keys = (ts: { idempotency_key: string }[]) => ts.map((t) => t.idempotency_key).join(",");
async function mk(ctx: Ctx, over: Record<string, unknown> = {}) { const r = await createMission(ctx, { ...INPUT, ...over }); if (!r.ok) throw new Error(r.error); return r.mission.id; }
async function run(ctx: Ctx, id: string, key: string, review = true) {
  const r = await reserveCost(ctx, WS, id, key); if (!r.ok) throw new Error(r.error);
  const c = await completeTask(ctx, WS, id, key, { answer: key }); if (!c.ok) throw new Error(c.error);
  if (review) { const v = await reviewTask(ctx, WS, id, key, { reviewer_role: reviewerFor(c.task.role), verdict: "pass" }); if (!v.ok) throw new Error(v.error); }
}

(async () => {
  // ---- create + idempotency
  {
    const { ctx, store } = world();
    const a = await createMission(ctx, INPUT), b = await createMission(ctx, INPUT);
    ok(a.ok && b.ok && a.created && !b.created && a.mission.id === b.mission.id && store.rows.filter((r) => r.kind === "mission").length === 1, "createMission: the same request never makes a second mission");
    ok(a.ok && a.mission.status === "queued" && a.mission.spent_usd === 0 && toolAllowed(a.mission, "search_tenders") && !toolAllowed(a.mission, "send_email"), "createMission: queued, nothing spent, only the allowed tools");
    ok(!(await createMission(ctx, { ...INPUT, type: "other" as never })).ok && !(await createMission(ctx, { ...INPUT, cost_budget_usd: -1 })).ok && !(await createMission(ctx, { ...INPUT, goal: " " })).ok, "createMission: rejects an unknown type, a negative budget, an empty goal");
    const id = a.ok ? a.mission.id : "";
    const t1 = await addTask(ctx, WS, id, { idempotency_key: "k1", role: "tender_project", question: "What does the tender require?", cost_reservation_usd: 1 });
    const t2 = await addTask(ctx, WS, id, { idempotency_key: "k1", role: "osint", question: "a different question under the same key", cost_reservation_usd: 5 });
    const m = (await loadMission(ctx, WS, id))!;
    ok(t1.ok && t2.ok && t1.created && !t2.created && m.tasks.length === 1 && m.tasks[0].role === "tender_project" && t2.task.question === "What does the tender require?", "addTask: the same idempotency key never creates a second task");
    ok(!(await addTask(ctx, WS, id, { idempotency_key: "k2", role: "nobody" as never, question: "q" })).ok && !(await addTask(ctx, WS, id, { idempotency_key: "", role: "osint", question: "q" })).ok && !(await addTask(ctx, WS, id, { idempotency_key: "k3", role: "osint", question: "q", depends_on: ["missing"] })).ok, "addTask: rejects an unknown role, an empty key, an unknown dependency");
    ok((await loadMission(ctx, "acme", id)) === null && !(await addTask(ctx, "acme", id, { idempotency_key: "x", role: "osint", question: "q" })).ok, "workspaces are isolated");
  }

  // ---- dependencies
  {
    const { ctx } = world();
    const id = await mk(ctx);
    await addTask(ctx, WS, id, { idempotency_key: "tender", role: "tender_project", question: "Requirements?", cost_reservation_usd: 1 });
    await addTask(ctx, WS, id, { idempotency_key: "osint", role: "osint", question: "Who is the buyer?", cost_reservation_usd: 1 });
    await addTask(ctx, WS, id, { idempotency_key: "sourcing", role: "technical_sourcing", question: "Which makers fit?", depends_on: ["tender"], cost_reservation_usd: 1 });
    await addTask(ctx, WS, id, { idempotency_key: "finance", role: "finance", question: "Landed cost?", depends_on: ["sourcing", "osint"], cost_reservation_usd: 1 });
    let m = (await loadMission(ctx, WS, id))!;
    ok(keys(nextRunnable(m)) === "tender,osint", "dependencies: only tasks without open dependencies are runnable");
    ok(!(await reserveCost(ctx, WS, id, "sourcing")).ok, "dependencies: a task cannot start before its dependency");
    await run(ctx, id, "tender", false);
    m = (await loadMission(ctx, WS, id))!;
    ok(keys(nextRunnable(m)) === "osint" && keys(awaitingReview(m)) === "tender", "dependencies: a completed but unreviewed task does not release its dependants");
    await reviewTask(ctx, WS, id, "tender", { reviewer_role: "red_team", verdict: "pass" });
    m = (await loadMission(ctx, WS, id))!;
    ok(keys(nextRunnable(m)) === "osint,sourcing", "dependencies: after a passed review the dependant is runnable");
    await run(ctx, id, "sourcing");
    ok(keys(nextRunnable((await loadMission(ctx, WS, id))!)) === "osint", "dependencies: a task with two dependencies waits for both");
    await run(ctx, id, "osint");
    ok(keys(nextRunnable((await loadMission(ctx, WS, id))!)) === "finance", "dependencies: runnable when all are done");
    await run(ctx, id, "finance");
    m = (await loadMission(ctx, WS, id))!;
    ok(m.status === "completed" && m.spent_usd === 4 && nextRunnable(m).length === 0, "mission completes when every task is completed and reviewed; cost is summed");
    ok(!(await addTask(ctx, WS, id, { idempotency_key: "late", role: "osint", question: "q" })).ok, "a completed mission takes no new tasks");
  }

  // ---- budget exhaustion
  {
    const { ctx } = world();
    const id = await mk(ctx, { cost_budget_usd: 5 });
    await addTask(ctx, WS, id, { idempotency_key: "a", role: "osint", question: "q", cost_reservation_usd: 3 });
    await addTask(ctx, WS, id, { idempotency_key: "b", role: "finance", question: "q", cost_reservation_usd: 3 });
    await addTask(ctx, WS, id, { idempotency_key: "c", role: "tender_project", question: "q", cost_reservation_usd: 2 });
    const ra = await reserveCost(ctx, WS, id, "a");
    ok(ra.ok && ra.reserved_usd === 3 && reservedUsd(ra.mission) === 3 && remainingUsd(ra.mission) === 2 && ra.mission.status === "running", "budget: a reservation is held while the task runs");
    const rb = await reserveCost(ctx, WS, id, "b");
    let m = (await loadMission(ctx, WS, id))!;
    ok(!rb.ok && m.status === "needs_owner" && m.next_decision.startsWith("budget") && m.tasks[1].status === "queued" && m.tasks[1].attempt === 0, "budget: a reservation that would exceed the budget is refused and the mission needs the owner");
    ok(nextRunnable(m).length === 0 && !(await reserveCost(ctx, WS, id, "c")).ok, "budget: nothing starts while the mission needs the owner");
    const ca = await completeTask(ctx, WS, id, "a", "out", 1.5);
    ok(ca.ok && ca.mission.spent_usd === 1.5 && ca.mission.status === "needs_owner", "budget: a running task may still report; the real cost is recorded");
    await resume(ctx, WS, id);
    const rb2 = await reserveCost(ctx, WS, id, "b");
    ok(rb2.ok && remainingUsd(rb2.mission) === 0.5, "budget: after resume the task fits because the real cost was lower");
    const rc = await reserveCost(ctx, WS, id, "c");
    ok(!rc.ok && (await loadMission(ctx, WS, id))!.status === "needs_owner", "budget: the next one is refused again");
    await setBudget(ctx, WS, id, 8); await resume(ctx, WS, id);
    ok((await reserveCost(ctx, WS, id, "c")).ok, "budget: the owner raises the budget and the task starts");
    m = (await loadMission(ctx, WS, id))!;
    ok(m.spent_usd + reservedUsd(m) <= m.cost_budget_usd, "budget: spent plus reserved never exceeds the budget");
  }

  // ---- retries
  {
    const { ctx } = world();
    const id = await mk(ctx);
    await addTask(ctx, WS, id, { idempotency_key: "r", role: "osint", question: "q", max_attempts: 3, cost_reservation_usd: 1 });
    await reserveCost(ctx, WS, id, "r");
    const f1 = await failTask(ctx, WS, id, "r", "timeout", 0.2);
    ok(f1.ok && f1.will_retry && f1.task.status === "queued" && f1.task.attempt === 1 && f1.mission.spent_usd === 0.2 && f1.mission.status === "running", "retries: a failed attempt goes back to queued and its cost is recorded");
    ok(!(await failTask(ctx, WS, id, "r", "again")).ok, "retries: only a running task can fail");
    await reserveCost(ctx, WS, id, "r");
    const f2 = await failTask(ctx, WS, id, "r", "timeout");
    await reserveCost(ctx, WS, id, "r");
    const f3 = await failTask(ctx, WS, id, "r", "timeout");
    ok(f2.ok && f2.will_retry && f3.ok && !f3.will_retry && f3.task.status === "failed" && f3.task.attempt === 3, "retries: after max_attempts the task is failed");
    ok(f3.ok && f3.mission.status === "failed" && f3.mission.next_decision.includes("r failed after 3") && !(await reserveCost(ctx, WS, id, "r")).ok, "retries: the mission is failed and the task does not start again");
  }

  // ---- restart safety
  {
    const { ctx, store } = world();
    const plan = async (c: Ctx) => {
      const id = await mk(c);
      await addTask(c, WS, id, { idempotency_key: "tender", role: "tender_project", question: "Requirements?", cost_reservation_usd: 1 });
      await addTask(c, WS, id, { idempotency_key: "sourcing", role: "technical_sourcing", question: "Makers?", depends_on: ["tender"], cost_reservation_usd: 1 });
      return id;
    };
    const id = await plan(ctx);
    const first = await reserveCost(ctx, WS, id, "tender");
    // the process dies here; a new one starts with the same store and replays the whole plan
    const ctx2: Ctx = { store, now: () => Date.parse("2026-11-11T12:00:00Z") };
    const id2 = await plan(ctx2);
    let m = (await loadMission(ctx2, WS, id2))!;
    ok(id2 === id && m.tasks.length === 2 && store.rows.filter((r) => r.kind === "task" && r.rev === 1).length === 2, "restart: replaying the plan against the same store duplicates nothing");
    ok(m.status === "running" && m.tasks[0].status === "running" && m.tasks[0].attempt === 1, "restart: the rebuilt state keeps the running task and its attempt");
    const again = await reserveCost(ctx2, WS, id, "tender");
    ok(first.ok && again.ok && again.already && again.task.attempt === 1 && reservedUsd(again.mission) === 1, "restart: reserving a running task again neither double-reserves nor counts a new attempt");
    await completeTask(ctx2, WS, id, "tender", "out");
    const twice = await completeTask(ctx2, WS, id, "tender", "out again");
    m = (await loadMission(ctx2, WS, id))!;
    ok(twice.ok && twice.already && m.spent_usd === 1 && m.tasks[0].output === "out", "restart: completing twice charges once and keeps the first output");
    const before = JSON.stringify(m);
    ok(JSON.stringify(await loadMission({ store, now: () => 0 }, WS, id)) === before, "restart: rebuilding from the store is repeatable");
  }

  // ---- reviewer rule
  {
    const { ctx } = world();
    const id = await mk(ctx);
    await addTask(ctx, WS, id, { idempotency_key: "fin", role: "finance", question: "q", max_attempts: 2 });
    await addTask(ctx, WS, id, { idempotency_key: "rt", role: "red_team", question: "attack the plan" });
    ok(!(await reviewTask(ctx, WS, id, "fin", { reviewer_role: "red_team", verdict: "pass" })).ok, "review: only a completed task can be reviewed");
    await run(ctx, id, "fin", false); await run(ctx, id, "rt", false);
    const self = await reviewTask(ctx, WS, id, "fin", { reviewer_role: "finance", verdict: "pass" });
    ok(!self.ok && self.error.includes("cannot be reviewed by the same role"), "review: a task produced by a role cannot be reviewed by the same role");
    ok(!(await reviewTask(ctx, WS, id, "fin", { reviewer_role: "osint", verdict: "pass" })).ok, "review: red_team reviews, not another specialist");
    const rtSelf = await reviewTask(ctx, WS, id, "rt", { reviewer_role: "red_team", verdict: "pass" });
    ok(!rtSelf.ok && rtSelf.error.includes("same role") && reviewerFor("red_team") === "source_evidence", "review: red_team cannot review its own task");
    ok(MISSION_ROLES.every((r) => reviewerFor(r) !== r), "review: no role is its own reviewer");
    const bad = await reviewTask(ctx, WS, id, "fin", { reviewer_role: "red_team", verdict: "fail", notes: "margin has no source" });
    ok(bad.ok && bad.task.status === "queued" && bad.task.reviewer_result?.verdict === "fail" && bad.task.last_error.includes("margin has no source"), "review: a failed review sends the task back for another attempt");
    await run(ctx, id, "fin", false);
    ok(!(await loadMission(ctx, WS, id))!.tasks[0].reviewer_result, "review: the new attempt needs a new review");
    await reviewTask(ctx, WS, id, "fin", { reviewer_role: "red_team", verdict: "pass" });
    ok(!(await reviewTask(ctx, WS, id, "fin", { reviewer_role: "red_team", verdict: "fail" })).ok, "review: a reviewed task is not reviewed twice");
    ok((await loadMission(ctx, WS, id))!.status === "running", "review: the mission is not complete while a review is open");
    const last = await reviewTask(ctx, WS, id, "rt", { reviewer_role: "source_evidence", verdict: "pass" });
    ok(last.ok && last.mission.status === "completed", "review: the mission completes after the last review passes");
    // a second failed review at max_attempts fails the task
    const id2 = await mk(ctx, { goal: "second fixture mission" });
    await addTask(ctx, WS, id2, { idempotency_key: "one", role: "osint", question: "q", max_attempts: 1 });
    await run(ctx, id2, "one", false);
    const rej = await reviewTask(ctx, WS, id2, "one", { reviewer_role: "red_team", verdict: "fail" });
    ok(rej.ok && rej.task.status === "failed" && rej.mission.status === "failed", "review: a failed review with no attempts left fails the task and the mission");
  }

  // ---- pause / resume / cancel / wait
  {
    const { ctx } = world();
    const id = await mk(ctx);
    await addTask(ctx, WS, id, { idempotency_key: "a", role: "osint", question: "q", cost_reservation_usd: 1 });
    await addTask(ctx, WS, id, { idempotency_key: "b", role: "finance", question: "q", cost_reservation_usd: 1 });
    await reserveCost(ctx, WS, id, "a");
    const p = await pause(ctx, WS, id, "sanctions hit");
    ok(p.ok && p.mission.status === "paused_on_risk" && nextRunnable(p.mission).length === 0 && !(await reserveCost(ctx, WS, id, "b")).ok, "pause: paused on risk, nothing new starts");
    const r = await resume(ctx, WS, id);
    ok(r.ok && r.mission.status === "running" && keys(nextRunnable(r.mission)) === "b" && !(await resume(ctx, WS, id)).ok, "resume: continues; resume of a running mission is refused");
    const w = await waitOnExternal(ctx, WS, id, "supplier reply");
    ok(w.ok && w.mission.status === "waiting_on_external" && nextRunnable(w.mission).length === 0 && (await resume(ctx, WS, id)).ok, "wait: waiting on external stops new starts until resume");
    const c = await cancel(ctx, WS, id, "owner cancelled");
    ok(c.ok && c.mission.status === "cancelled" && c.mission.tasks.every((t) => t.status === "cancelled"), "cancel: the mission and its open tasks are cancelled");
    ok(!(await resume(ctx, WS, id)).ok && !(await pause(ctx, WS, id, "x")).ok && !(await reserveCost(ctx, WS, id, "b")).ok && !(await completeTask(ctx, WS, id, "a", "late")).ok && (await cancel(ctx, WS, id)).ok, "cancel: final; nothing resumes, starts or completes afterwards");
    const id3 = await mk(ctx, { goal: "untouched fixture mission" });
    await pause(ctx, WS, id3, "risk");
    ok((await resume(ctx, WS, id3)).mission?.status === "queued", "resume: a mission that never started goes back to queued");
  }

  // ---- personas
  {
    const ids = new Set(TEAM.map((m) => m.id));
    const mapped = Object.values(ROLE_PERSONAS).flat();
    ok(Object.keys(ROLE_PERSONAS).length === 10 && MISSION_ROLES.length === 10 && MISSION_ROLES.every((r) => Array.isArray(ROLE_PERSONAS[r])), "personas: all ten roles are mapped");
    ok(mapped.every((id) => ids.has(id)), "personas: every mapped persona exists in lib/team.ts");
    ok(TEAM.every((m) => mapped.includes(m.id)), "personas: every team member belongs to a role");
    ok(ROLE_PERSONAS.regional_relations.length === 6 && ROLE_PERSONAS.regional_relations.every((id) => id.startsWith("relations_")) && roleOfPersona("relations_mena") === "regional_relations", "personas: the six regional personas map to regional_relations");
    ok(personasFor("finance")[0]?.name === "Helena Lindqvist" && roleOfPersona("evidence") === "source_evidence" && ROLE_PERSONAS.red_team.length === 0, "personas: lookups work; red_team has no outward persona");
  }

  console.log(fail ? `\n${fail} FAILED` : "\nall passed");
  process.exit(fail ? 1 : 0);
})();
