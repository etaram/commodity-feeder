// The deterministic mission runner (lib/missionrun.ts) on an in-memory store with fixture deal files, a fixture
// supplier index and a fixture sanctions index. No network, no model, nothing is sent.
import type { DealRecord, Kind } from "@/lib/deal";
import { auditMayCall } from "@/lib/auditscope";
import { completeTask, createMission, loadMission, MemoryMissionStore, reserveCost, resume, ROLE_PERSONAS, type Mission, type MissionType } from "@/lib/mission";
import { PLANS, planMission, redTeam, reviewOutput, runNext, stepOf, type Candidate, type RunContext, type RunDeps, type TaskOutput } from "@/lib/missionrun";
import { missionView } from "@/lib/missionview";
import { evaluateRoute, STATE_RANK, type OpportunityRoute, type RouteState } from "@/lib/route";
import { screenWith, type SanctionsIndex } from "@/lib/sanctions";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const WS = "sinder", DEAL = "T-FIXTURE-9", NOW = "2026-11-11T09:00:00.000Z";
let seq = 0;
const rec = (kind: Kind, record_id: string, data: Record<string, unknown>): DealRecord =>
  ({ time: `2026-11-10 10:00:${String(seq++).padStart(2, "0")}`, deal_id: DEAL, kind, record_id, version: 1, status: String(data.status || ""), data, by: "analyst@example.org", source: "panel", note: "" });
const TENDER = { stage: "awarded", deadline: "2026-10-01", buyer: "Fixture Water Board", title: "Supply of dosing pumps", link: "https://tenders.example.org/notice/9" };
const AWARD = { winner: "Fixture Contractors Ltd", source: "https://awards.example.org/award/9", date: "2026-11-01" };
const PUMPS: Candidate = { name: "Fixture Pumps Ltd", country: "CHN", match: { bucket: "supported", why: "its own product list names dosing pumps", evidence: "own website", conflicts: [], gaps: [], url: "https://fixturepumps.example/products" } };
const INDEX: SanctionsIndex = { updated: "2026-11-11 05:00", ents: [[["Bad Actor Trading LLC", "Bad Actor Co"], "OFAC SDN", "SDGT", "entity", "ref-123"]] };

type World = { store: MemoryMissionStore; deps: RunDeps; c: RunContext; set: { suppliers: Candidate[] | null; index: SanctionsIndex | null }; calls: { suppliers: number; screen: number; context: number } };
function world(over: Partial<RunContext> = {}): World {
  const store = new MemoryMissionStore(), clock = { t: Date.parse(NOW) };
  const c: RunContext = { now: NOW, records: [rec("stage", "stage", { stage: "sourcing", title: "Dosing pumps for Fixture Water Board", deadline: "2026-12-20" })], tender: { ...TENDER }, award: { ...AWARD }, comparison: null, ...over };
  const set = { suppliers: [PUMPS] as Candidate[] | null, index: INDEX as SanctionsIndex | null }, calls = { suppliers: 0, screen: 0, context: 0 };
  const deps: RunDeps = { store, now: () => (clock.t += 1000), workspace: WS,
    context: async () => { calls.context++; return c; },
    suppliers: async () => { calls.suppliers++; return set.suppliers; },
    screen: async (parties, now) => { calls.screen++; return screenWith(set.index, parties, now); } };
  return { store, deps, c, set, calls };
}
async function mission(w: World, type: MissionType = "supply_winner", goal = "Supply the winner of fixture award 9"): Promise<string> {
  const r = await createMission(w.deps, { workspace: WS, type, goal, represented_org: WS, deal_id: DEAL, cost_budget_usd: 5 });
  if (!r.ok) throw new Error(r.error);
  return r.mission.id;
}
const get = async (w: World, id: string) => (await loadMission(w.deps, WS, id)) as Mission;
const out = (m: Mission, step: string) => (m.tasks.find((t) => stepOf(t) === step)?.output || null) as TaskOutput | null;
const task = (m: Mission, step: string) => m.tasks.find((t) => stepOf(t) === step)!;
const doneSteps = (m: Mission) => m.tasks.filter((t) => t.status === "completed").map((t) => stepOf(t)).join(",");
async function steps(w: World, id: string, n: number) { let last = await runNext(id, w.deps); for (let i = 1; i < n; i++) last = await runNext(id, w.deps); return last; }

(async () => {
  // ---- plan per type
  {
    const m = { id: "MIS-x", type: "supply_winner" as const, deal_id: DEAL };
    const p = planMission(m, { tender: TENDER });
    ok(p.map((t) => t.idempotency_key.split(":").pop()).join() === "award_verification,procurement_hypothesis,supplier_match,sanctions_screen,economics,route_evaluation,independent_review,owner_decision",
      "supply_winner: award, hypothesis, supplier match, sanctions, economics, route, independent review, owner decision");
    ok(p.map((t) => t.role).join() === "source_evidence,tender_project,technical_sourcing,logistics_compliance,finance,commercial_strategy,red_team,commercial_strategy", "each step is given to its role");
    ok(p[0].depends_on!.length === 0 && p.slice(1).every((t, i) => t.depends_on!.length === 1 && t.depends_on![0] === p[i].idempotency_key), "each task depends on the one before it");
    ok(new Set(p.map((t) => t.idempotency_key)).size === p.length && p.every((t) => t.idempotency_key.startsWith("MIS-x:") && t.cost_reservation_usd === 0) && JSON.stringify(planMission(m)) === JSON.stringify(planMission(m)),
      "idempotency keys are unique, stable and tied to the mission; a code task reserves 0 USD");
    ok(/not confirmed demand/.test(p[1].question) && p[0].question.includes("Supply of dosing pumps"), "the hypothesis task says so in its own question; the notice title is named");
    for (const type of ["win_tender", "supply_winner", "client_bd", "strategic_signal"] as const) {
      const q = planMission({ id: "M", type, deal_id: "" }), names = q.map((t) => t.idempotency_key.split(":").pop());
      ok(names.join() === PLANS[type].join() && names[names.length - 1] === "owner_decision" && names[names.length - 2] === "independent_review" && q.every((t) => ROLE_PERSONAS[t.role] !== undefined),
        `${type}: ${names.length} tasks, ending with the independent review and the owner's decision`);
    }
    ok(PLANS.win_tender[0] === "notice_verification" && PLANS.win_tender.includes("requirements_reading") && PLANS.client_bd[0] === "prospect_verification" && PLANS.strategic_signal[0] === "signal_verification"
      && !PLANS.strategic_signal.includes("route_evaluation"), "each type starts by verifying its own source; a strategic signal builds no route");
  }

  // ---- supply_winner end to end, one step per call
  {
    const w = world(), id = await mission(w);
    const r1 = await runNext(id, w.deps);
    let m = await get(w, id);
    ok(r1.ok && r1.ran === `${id}:award_verification` && m.tasks.length === 8 && doneSteps(m) === "award_verification" && m.status === "running", "the first call plans 8 tasks and runs exactly one");
    const a = out(m, "award_verification")!;
    ok(a.claims.every((c) => c.source.startsWith("https://")) && a.claims.some((c) => c.text.includes("Fixture Contractors Ltd") && c.source === AWARD.source) && task(m, "award_verification").reviewer_result?.verdict === "pass"
      && task(m, "award_verification").reviewer_result?.reviewer_role === "red_team", "award verification: every claim carries its source; reviewed by red_team, not by its own role");
    await runNext(id, w.deps); m = await get(w, id);
    const h = out(m, "procurement_hypothesis")!;
    ok(doneSteps(m) === "award_verification,procurement_hypothesis" && /not confirmed demand/i.test(h.summary) && h.claims[0].basis === "hypothesis" && h.data.confirmed === false && h.open_questions.length === 1,
      "the remaining procurement is recorded as a hypothesis: \"not confirmed demand\", with the question only the winner can answer");
    await runNext(id, w.deps); m = await get(w, id);
    const sm = out(m, "supplier_match")!;
    ok((sm.data.proposed as { name: string; fit: string }).name === "Fixture Pumps Ltd" && (sm.data.proposed as { fit: string }).fit === "supported" && sm.claims[0].basis === "supplier-index" && /selected by nobody/.test(sm.summary),
      "supplier match carries the index candidate forward with its supmatch bucket, and says nobody selected it");
    await runNext(id, w.deps); m = await get(w, id);
    const sc = out(m, "sanctions_screen")!;
    ok(sc.data.status === "CHECKED_NO_ISSUE" && /no candidate match on 2026-11-11/.test(sc.summary) && /not a clearance/.test(sc.summary) && sc.data.clearance === false && m.status === "running", "no candidate: \"checked, no candidate match on <date>\", stated as not a clearance");
    ok(JSON.stringify(sc.data.screened).includes("Fixture Water Board") && JSON.stringify(sc.data.screened).includes("Fixture Contractors Ltd") && JSON.stringify(sc.data.screened).includes("Fixture Pumps Ltd"), "buyer, winner and supplier names are all screened");
    await runNext(id, w.deps); m = await get(w, id);
    const ec = out(m, "economics")!, inputs = ec.data.inputs as Record<string, number | null>;
    ok(inputs.sale_price === null && inputs.cost_goods === null && ec.data.margin === null && ec.data.peak_funding === null && ec.data.funding_capacity === "unknown", "economics with no inputs: every number stays null, nothing is assumed");
    ok(ec.open_questions.some((q) => /What is the sale price\?/.test(q)) && ec.open_questions.some((q) => /quoted price/.test(q)) && m.status === "running", "unknown finance inputs become questions and do not stop the research");
    await runNext(id, w.deps); m = await get(w, id);
    const ro = out(m, "route_evaluation")!, route = ro.data.route as OpportunityRoute, state = ro.data.state as RouteState;
    ok(route.route_type === "supply_winner" && route.demand.status === "awarded" && route.supply.supplier === "Fixture Pumps Ltd" && route.authority.sanctions_alert === false && route.authority.owner_mandate === "none",
      "the route is built from the deal file and the earlier tasks: supply_winner, awarded, the carried supplier, no mandate");
    ok(state === evaluateRoute(route).state && STATE_RANK[state] >= STATE_RANK.READY_FOR_OWNER_REVIEW, `the state is what the gates give (${state}) and never above owner review without a mandate`);
    const r7 = await runNext(id, w.deps); m = await get(w, id);
    const rv = out(m, "independent_review")!;
    ok(r7.ran === `${id}:independent_review` && rv.data.verdict === "pass" && (rv.data.checked as string[]).length === 6 && task(m, "independent_review").reviewer_result?.reviewer_role === "source_evidence",
      "the independent review covers the six earlier outputs and passes; its own work is reviewed by source_evidence");
    const r8 = await runNext(id, w.deps); m = await get(w, id);
    ok(r8.ran === `${id}:owner_decision` && m.status === "needs_owner" && m.next_decision.startsWith("owner: ") && m.next_decision.includes(`Route state ${state}`) && /Sanctions: CHECKED_NO_ISSUE/.test(m.next_decision) && /not a clearance/.test(m.next_decision),
      "the mission ends at needs_owner with the next decision for the owner, not at completed");
    ok(m.tasks.every((t) => t.status === "completed" && t.attempt === 1) && m.spent_usd === 0 && m.cost_budget_usd === 5, "eight tasks completed once each; 0 USD reserved and spent");
    ok(m.tasks.every((t) => (t.output as TaskOutput).claims.length > 0 && (t.output as TaskOutput).claims.every((c) => c.source && c.basis)), "every recorded claim has a source and a basis label");
    // nothing more runs, and nothing is written twice
    const rows = w.store.rows.length, calls = { ...w.calls };
    const again = await runNext(id, w.deps), again2 = await runNext(id, w.deps);
    m = await get(w, id);
    ok(again.ran === null && again2.ran === null && m.status === "needs_owner" && m.tasks.length === 8 && w.calls.suppliers === calls.suppliers && w.calls.screen === calls.screen
      && w.store.rows.filter((r) => r.kind === "task").length === w.store.rows.slice(0, rows).filter((r) => r.kind === "task").length, "further calls run nothing and write no task row: the decision waits for the owner");
    const v = missionView(m);
    ok(v.task_list.length === 8 && v.task_list.every((t) => t.persona.length > 0 && t.status === "completed"), "the view names a persona or the internal review for each task");
    ok(v.task_list[2].persona.includes("Daniel Okafor") && v.task_list[6].persona === "internal review (no persona)" && v.task_list[3].sources.length === 1 && v.task_list[1].summary.includes("not confirmed demand"),
      "the view: persona by role (none for the red team), output summary and sources");
  }

  // ---- restart safety
  {
    const w = world(), id = await mission(w);
    await runNext(id, w.deps);
    // a crash after the reservation: the task is running, nothing is recorded
    await reserveCost(w.deps, WS, id, `${id}:procurement_hypothesis`);
    ok(task(await get(w, id), "procurement_hypothesis").status === "running", "fixture: a task left running by a crash");
    const fresh: RunDeps = { ...w.deps }; // a new process, the same store
    const r = await runNext(id, fresh);
    let m = await get(w, id);
    ok(r.ran === `${id}:procurement_hypothesis` && task(m, "procurement_hypothesis").status === "completed" && task(m, "procurement_hypothesis").attempt === 1 && doneSteps(m) === "award_verification,procurement_hypothesis",
      "after a restart the running task is finished once, in the same attempt");
    // a crash after the output was recorded and before the review
    const key = `${id}:supplier_match`;
    await reserveCost(w.deps, WS, id, key);
    await completeTask(w.deps, WS, id, key, { step: "supplier_match", version: "fixture", at: NOW, summary: "fixture output", claims: [{ text: "Fixture Pumps Ltd: supported", source: "https://fixturepumps.example/products", basis: "supplier-index" }],
      sources: ["https://fixturepumps.example/products"], open_questions: [], stop: null, data: { proposed: { name: "Fixture Pumps Ltd", fit: "supported" } } }, 0);
    const before = w.calls.suppliers;
    const r2 = await runNext(id, fresh);
    m = await get(w, id);
    ok(r2.ran === key && w.calls.suppliers === before && (out(m, "supplier_match") as TaskOutput).version === "fixture" && task(m, "supplier_match").reviewer_result?.verdict === "pass" && doneSteps(m).split(",").length === 3,
      "a completed, unreviewed task is reviewed, not executed again: its output is not replaced or duplicated");
    const completedRows = (k: string) => w.store.rows.filter((x) => x.kind === "task" && x.id === k && x.data.status === "completed" && !x.data.reviewer_result).length;
    ok(completedRows(`${id}:award_verification`) === 1 && completedRows(`${id}:procurement_hypothesis`) === 1 && completedRows(key) === 1, "each output was written exactly once");
    const twice = await createMission(w.deps, { workspace: WS, type: "supply_winner", goal: "Supply the winner of fixture award 9", represented_org: WS, deal_id: DEAL, cost_budget_usd: 5 });
    await runNext(id, w.deps);
    ok(twice.ok && !twice.created && (await get(w, id)).tasks.length === 8, "the same mission request and a re-plan never add a second task list");
    ok((await runNext("MIS-nope", w.deps)).ok === false && (await runNext(id, { ...w.deps, workspace: "acme" })).mission === null, "an unknown mission, or one of another workspace, is not found");
  }

  // ---- a sanctions candidate pauses the mission and is never cleared
  {
    const w = world();
    w.set.suppliers = [{ ...PUMPS, name: "Bad Actor Trading LLC" }];
    const id = await mission(w);
    const r = await steps(w, id, 4);
    let m = await get(w, id);
    ok(r.ran === `${id}:sanctions_screen` && m.status === "paused_on_risk" && /qualified review required/.test(m.next_decision) && /Bad Actor Trading LLC/.test(m.next_decision), "a candidate match pauses the mission: qualified review required");
    const sc = out(m, "sanctions_screen")!;
    ok(sc.data.status === "FAILED" && (sc.data.candidates as unknown[]).length >= 1 && sc.claims[0].basis === "name-screening" && /never cleared automatically/.test(sc.summary), "the candidate is recorded with the list and reference, as a lead to verify");
    w.set.index = { updated: "2026-11-11 08:00", ents: [] }; // the list changes later: the pause does not lift
    const n = w.calls.screen;
    const p1 = await runNext(id, w.deps), p2 = await runNext(id, w.deps);
    m = await get(w, id);
    ok(p1.ran === null && p2.ran === null && m.status === "paused_on_risk" && w.calls.screen === n && doneSteps(m).split(",").length === 4 && /never clears/.test(p1.note), "running again never clears it: no step runs, no new screen is made");
    // even if a person resumes the mission through the library, the route stays stopped
    await resume(w.deps, WS, id);
    await steps(w, id, 2);
    m = await get(w, id);
    const ro = out(m, "route_evaluation")!;
    ok(ro.data.state === "STOPPED" && (ro.data.route as OpportunityRoute).authority.sanctions_alert === true && redTeam(m).findings.length === 0, "after a manual resume the recorded alert still stops the route (STOPPED)");
    await steps(w, id, 2);
    m = await get(w, id);
    ok(m.status === "needs_owner" && /Sanctions: FAILED \(qualified review required\)/.test(m.next_decision) && /stopped/i.test(m.next_decision), "the owner's decision names the alert and asks for qualified review");
  }
  // lists unavailable or out of date: not checked, nothing continues unscreened
  {
    const w = world(); w.set.index = null;
    const id = await mission(w);
    await steps(w, id, 4);
    let m = await get(w, id);
    ok(m.status === "waiting_on_external" && /NOT_CHECKED/.test(m.next_decision) && task(m, "sanctions_screen").status === "queued" && task(m, "sanctions_screen").output === null && task(m, "sanctions_screen").attempt === 0,
      "lists unreadable: NOT_CHECKED, the mission waits and the task records nothing");
    w.set.index = { updated: "2026-10-01 05:00", ents: [] };
    await runNext(id, w.deps); m = await get(w, id);
    ok(m.status === "waiting_on_external" && /STALE/.test(m.next_decision) && doneSteps(m).split(",").length === 3, "an index older than three days does not count as a check (STALE)");
    w.set.index = INDEX;
    const r = await runNext(id, w.deps); m = await get(w, id);
    ok(r.ran === `${id}:sanctions_screen` && m.status === "running" && out(m, "sanctions_screen")!.data.status === "CHECKED_NO_ISSUE", "when the current index answers, the same step runs");
  }

  // ---- missing inputs: needs_owner / waiting_on_external with a concrete question, and nothing faked
  {
    const w = world({ award: null }), id = await mission(w);
    const r = await runNext(id, w.deps);
    let m = await get(w, id);
    ok(r.ran === null && m.status === "needs_owner" && /Who won/.test(m.next_decision) && m.next_decision.includes(DEAL) && task(m, "award_verification").status === "queued" && task(m, "award_verification").output === null,
      `no winner in the awards index: needs_owner with the question ("${m.next_decision.slice(7, 80)}..."), no output invented`);
    await runNext(id, w.deps); m = await get(w, id);
    ok(m.status === "needs_owner" && /Who won/.test(m.next_decision) && task(m, "award_verification").attempt === 0, "asking again without the answer brings the same question back and uses no attempt");
    w.c.award = { ...AWARD };
    const r2 = await runNext(id, w.deps); m = await get(w, id);
    ok(r2.ran === `${id}:award_verification` && m.status === "running" && doneSteps(m) === "award_verification", "once the award is in the index the step runs");
  }
  {
    const w = world({ tender: { ...TENDER, stage: "tender" } }), id = await mission(w);
    await runNext(id, w.deps);
    const m = await get(w, id);
    ok(m.status === "waiting_on_external" && /Has the award been published, and who won\?/.test(m.next_decision), "supply to the winner before the award: waiting_on_external, with the question");
    const w2 = world({ tender: null }), id2 = await mission(w2);
    await runNext(id2, w2.deps);
    ok((await get(w2, id2)).status === "needs_owner" && /Which official notice \(link\)/.test((await get(w2, id2)).next_decision), "no notice in the index: the owner is asked which notice, nothing is assumed");
  }
  {
    const w = world({ tender: { ...TENDER, stage: "tender", deadline: "2026-12-10" }, award: null }), id = await mission(w, "win_tender", "Win fixture tender 9");
    await steps(w, id, 2);
    let m = await get(w, id);
    ok(doneSteps(m) === "notice_verification" && m.status === "needs_owner" && /No requirement is recorded/.test(m.next_decision) && /Which mandatory requirements/.test(m.next_decision),
      "win_tender with no requirement on file: needs_owner; reading the documents is not faked");
    w.c.records.push(rec("requirement", "R1", { item: "flow rate 50 l/h", mandatory: true, status: "unknown", source_doc: "tender document section 3" }));
    w.set.suppliers = null;
    await steps(w, id, 2); m = await get(w, id);
    ok(doneSteps(m) === "notice_verification,requirements_reading" && out(m, "requirements_reading")!.claims[0].source === "tender document section 3" && m.status === "waiting_on_external" && /supplier index could not be read/.test(m.next_decision),
      "the requirement is read from the deal file with its source; an unreadable supplier index is waiting_on_external");
    w.set.suppliers = [];
    await steps(w, id, 6); m = await get(w, id);
    const ro = out(m, "route_evaluation")!;
    ok(m.status === "needs_owner" && doneSteps(m).split(",").length === 8 && (ro.data.route as OpportunityRoute).route_type === "prime_bid" && (ro.data.route as OpportunityRoute).supply.supplier === null && ro.data.state === "RESEARCH"
      && /no supplier candidate/i.test(out(m, "supplier_match")!.summary), `win_tender runs to the owner's decision with no supplier found (${ro.data.state}), and says so`);
  }
  {
    const w = world({ records: [rec("stage", "stage", { stage: "lead", title: "משאבות מינון" })], tender: { ...TENDER, title: "" } }), id = await mission(w);
    await steps(w, id, 3);
    const m = await get(w, id);
    ok(m.status === "needs_owner" && /not in Latin script/.test(m.next_decision) && /model call/.test(m.next_decision) && w.calls.suppliers === 0, "a product name that needs translation is a question for the owner, never a model call");
  }

  // ---- client_bd and strategic_signal
  {
    const w = world({ tender: null, award: null, records: [rec("stage", "stage", { stage: "lead", title: "Reverse osmosis membranes" }), rec("party", "PB", { role: "buyer", name: "Fixture Desalination Co", status: "candidate", source: "https://fixture-desal.example/about" })] });
    const id = await mission(w, "client_bd", "Develop Fixture Desalination as a buyer");
    await steps(w, id, 7);
    const m = await get(w, id);
    ok(m.status === "needs_owner" && doneSteps(m).split(",").length === 7 && /not confirmed demand/.test(out(m, "demand_hypothesis")!.summary) && (out(m, "route_evaluation")!.data.route as OpportunityRoute).route_type === "client_bd"
      && out(m, "prospect_verification")!.claims[0].source === "https://fixture-desal.example/about", "client_bd: the prospect with its source, a labelled hypothesis, a client_bd route, the owner's decision");
    const w2 = world({ tender: null, award: null, records: [rec("party", "PB", { role: "buyer", name: "No Source Co", status: "candidate" })] }), id2 = await mission(w2, "client_bd", "Develop No Source Co");
    await runNext(id2, w2.deps);
    ok((await get(w2, id2)).status === "needs_owner" && /has no source/.test((await get(w2, id2)).next_decision), "client_bd: a prospect without a source is a question, not a claim");
    const w3 = world({ tender: { ...TENDER, stage: "planned" }, award: null }), id3 = await mission(w3, "strategic_signal", "Watch the fixture pump programme");
    await steps(w3, id3, 5);
    const m3 = await get(w3, id3);
    ok(m3.status === "needs_owner" && m3.tasks.length === 5 && /hypothesis, not confirmed demand/.test(m3.next_decision) && /Sanctions: NOT_CHECKED/.test(m3.next_decision), "strategic_signal: ends as a hypothesis for the owner, sanctions stated as not checked");
  }

  // ---- the reviewer catches an unsourced claim
  {
    // (a) at the task's own review: the award has no source
    const w = world({ award: { ...AWARD, source: "" } }), id = await mission(w);
    const r = await runNext(id, w.deps);
    let m = await get(w, id);
    ok(/review failed/.test(r.note) && m.status === "needs_owner" && /has no source/.test(m.next_decision) && /red_team review of award_verification failed/.test(m.next_decision), "an award with no source fails the red_team review: needs_owner, with the claim named");
    ok(task(m, "award_verification").status === "queued" && task(m, "award_verification").reviewer_result?.verdict === "fail" && doneSteps(m) === "" && missionView(m).task_list[0].summary === "", "the unsourced output is not accepted and not shown as a result; nothing depends on it");
    w.c.award = { ...AWARD };
    await runNext(id, w.deps); m = await get(w, id);
    ok(m.status === "running" && task(m, "award_verification").attempt === 2 && task(m, "award_verification").reviewer_result?.verdict === "pass", "with the source supplied the second attempt passes");
  }
  {
    // (b) planted after the fact: a stored output is altered so that one claim has no source
    const w = world(), id = await mission(w);
    await steps(w, id, 6);
    const key = `${id}:procurement_hypothesis`, rows = w.store.rows.filter((x) => x.kind === "task" && x.id === key), lastRow = rows[rows.length - 1];
    const planted = JSON.parse(JSON.stringify(lastRow)); planted.rev = lastRow.rev + 1;
    planted.data.output.claims.push({ text: "The winner will buy 40 pumps within 30 days", source: "", basis: "" });
    w.store.rows.push(planted);
    const r = await runNext(id, w.deps);
    let m = await get(w, id);
    const rv = out(m, "independent_review")!, findings = rv.data.findings as { task: string; rule: string; detail: string }[];
    ok(r.ran === `${id}:independent_review` && rv.data.verdict === "fail" && findings.some((f) => f.task === key && f.rule === "no_source" && /40 pumps/.test(f.detail)), "the red team's independent review catches the planted unsourced claim and names it");
    ok(findings.some((f) => f.task === key && f.rule === "no_basis") && m.status === "needs_owner" && /red team found 2 problem/.test(m.next_decision), "the same claim is also a number without a basis label; the mission stops at needs_owner");
    await runNext(id, w.deps); m = await get(w, id);
    ok(m.status === "needs_owner" && /No recommendation: the independent review failed/.test(m.next_decision) && task(m, "owner_decision").status === "queued", "no recommendation is made on outputs that failed the review");
  }
  {
    // (c) the other rules, on a mission whose stored outputs are altered in memory
    const w = world(), id = await mission(w);
    await steps(w, id, 6);
    const m = await get(w, id);
    ok(redTeam(m).verdict === "pass", "untouched outputs pass");
    const up = JSON.parse(JSON.stringify(m)) as Mission; (out(up, "route_evaluation")!.data as { state: string }).state = "ACTIVE";
    ok(redTeam(up).findings.some((f) => f.rule === "state_above_gates" && /gates allow no more than/.test(f.detail)), "a state above what the gates allow is caught");
    const alert = JSON.parse(JSON.stringify(m)) as Mission; (out(alert, "sanctions_screen")!.data as { status: string }).status = "FAILED";
    ok(redTeam(alert).findings.some((f) => f.rule === "sanctions_not_reflected"), "a sanctions candidate that the route does not carry is caught");
    const hyp = JSON.parse(JSON.stringify(m)) as Mission; out(hyp, "procurement_hypothesis")!.summary = "The winner needs dosing pumps.";
    ok(redTeam(hyp).findings.some((f) => f.rule === "hypothesis_label"), "a hypothesis that drops \"not confirmed demand\" is caught");
    ok(reviewOutput("k", null)[0].rule === "empty" && reviewOutput("k", { ...out(m, "economics")!, claims: [{ text: "Sale price: 60000", source: "deal economics", basis: "guess", value: 60000 }] })[0].rule === "no_basis"
      && reviewOutput("k", { ...out(m, "economics")!, claims: [{ text: "Buyer named in the notice", source: "https://x.example", basis: "" }] }).length === 0, "an empty output fails; a number needs a basis label from the fixed list; a sourced statement without a number passes");
  }

  // ---- economics with recorded inputs and a quote comparison
  {
    const quote = rec("quote", "Q1", { supplier: "Fixture Pumps Ltd", product: "dosing pump", qty: 40, unit: "pcs", unit_price: 1200, currency: "USD", incoterm: "FOB", named_place: "Ningbo", availability: "confirmed", source_ref: "quotation QF-77 (pdf)" });
    const econ = rec("economics", "econ", { role: "principal", sale_price: 60000, cost_goods: 48000, freight: 2000, insurance: null, inspection: null, funding_limit: 40000, fin_rate_pct: 10, balance_day: 0, customer_day: 60 });
    const w = world({ records: [rec("stage", "stage", { stage: "sourcing", title: "Dosing pumps" }), quote, econ],
      comparison: { groups: [{ basis: "FOB ningbo", rows: [{ supplier: "Fixture Pumps Ltd", country: "", product: "dosing pump", incoterm: "FOB", place: "Ningbo", price: 1200, unit: "pcs", currency: "USD", usd: 1200, basis: "USD/pcs", vs_target_pct: null, lead_time_days: null, payment: "", valid_until: "", flags: [], rank: 1 }] }] } });
    const id = await mission(w);
    await steps(w, id, 6);
    const m = await get(w, id), ec = out(m, "economics")!;
    ok(ec.data.margin === 10000 && ec.data.cost === 50000 && Math.round(ec.data.peak_funding as number) === 50822 && Math.round(ec.data.finance_cost as number) === 822 && ec.data.funding_capacity === "exceeds the stated limit" && (ec.data.unknown as string[]).join() === "insurance,inspection",
      "economics: margin from the stated amounts, peak funding (with accrued financing) and capacity from cashCheck, missing items listed as unknown");
    ok(ec.claims.some((c) => c.basis === "quote" && c.source === "quotation QF-77 (pdf)" && c.value === 1200) && ec.claims.filter((c) => c.basis === "assumption").length >= 6 && ec.claims.some((c) => c.basis === "computed" && c.value === 10000) && /not a profit statement/.test(ec.summary),
      "each number carries its basis: quote, assumption or computed; the result is not called a profit statement");
    const route = out(m, "route_evaluation")!.data.route as OpportunityRoute;
    ok(Math.round(route.economics.capital_need as number) === 50822 && route.supply.supplier === "Fixture Pumps Ltd" && (out(m, "route_evaluation")!.data.blockers as { code: string }[]).some((b) => b.code === "funding_gap"), "the capital need reaches the route and the gates report the funding gap");
  }

  // ---- the audit session cannot run a step or write feedback
  ok(!auditMayCall("POST", "/api/missions/MIS-1/step") && !auditMayCall("POST", "/api/deal/feedback") && auditMayCall("GET", "/api/missions"), "audit session: reading missions is allowed, running a step and writing feedback are refused");
  if (fail) { console.log(`${fail} failed`); process.exit(1); }
})();
