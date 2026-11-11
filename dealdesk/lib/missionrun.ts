// The deterministic mission runner: plans a mission's tasks and executes them one at a time with existing code.
// No model call, no sending, no clock of its own (deps.now), no storage of its own (the injected mission store).
// Anything that would need a model or the outside world is not done and not faked: the step stops the mission at
// needs_owner or waiting_on_external with the precise question, and nothing is recorded on the task until the
// input exists. A sanctions candidate match pauses the mission (paused_on_risk): it is never cleared here.
//
// Every output is a list of claims; each claim carries its source and a basis label. Each completed task is checked
// at once by its reviewer role (red_team; red_team's own work by source_evidence) with the assertions below, and the
// plan's independent_review task runs the same assertions again over all outputs together, plus the cross checks
// (the route state is not above what the gates allow, a sanctions candidate is reflected in the route).
import { cashCheck } from "@/lib/dealstate";
import type { DealRecord } from "@/lib/deal";
import { addTask, completeTask, failTask, loadMission, needOwner, nextRunnable, pause, reserveCost, resume, reviewerFor, reviewTask, waitOnExternal,
  type Ctx, type Mission, type MissionRole, type MissionTask, type MissionType, type TaskInput } from "@/lib/mission";
import { evaluateRoute, STATE_RANK, STATES, type EvidenceItem, type OpportunityRoute, type RouteState, type RouteType, type TechnicalFit } from "@/lib/route";
import { chooseSupplier, dealParties, routeFromDeal, type DealContext, type QuoteComparison } from "@/lib/routemap";
import { SANCTIONS_SOURCE, type PartyScreen, type ScreenParty } from "@/lib/sanctions";
import { BUCKET_RANK, MATCH_VERSION, type MatchResult } from "@/lib/supmatch";

export const RUN_VERSION = "missionrun-1 (2026-11-11, deterministic, no model)";

export const STEPS = ["award_verification", "notice_verification", "signal_verification", "prospect_verification", "requirements_reading", "procurement_hypothesis",
  "demand_hypothesis", "supplier_match", "sanctions_screen", "economics", "route_evaluation", "independent_review", "owner_decision"] as const;
export type StepId = (typeof STEPS)[number];
const STEP_ROLE: Record<StepId, MissionRole> = { award_verification: "source_evidence", notice_verification: "source_evidence", signal_verification: "source_evidence",
  prospect_verification: "source_evidence", requirements_reading: "tender_project", procurement_hypothesis: "tender_project", demand_hypothesis: "tender_project",
  supplier_match: "technical_sourcing", sanctions_screen: "logistics_compliance", economics: "finance", route_evaluation: "commercial_strategy", independent_review: "red_team",
  owner_decision: "commercial_strategy" };
// The step order of each mission type. A step depends on the step before it, so the order is also the dependency chain.
export const PLANS: Record<MissionType, StepId[]> = {
  win_tender: ["notice_verification", "requirements_reading", "supplier_match", "sanctions_screen", "economics", "route_evaluation", "independent_review", "owner_decision"],
  supply_winner: ["award_verification", "procurement_hypothesis", "supplier_match", "sanctions_screen", "economics", "route_evaluation", "independent_review", "owner_decision"],
  client_bd: ["prospect_verification", "demand_hypothesis", "sanctions_screen", "economics", "route_evaluation", "independent_review", "owner_decision"],
  strategic_signal: ["signal_verification", "demand_hypothesis", "supplier_match", "independent_review", "owner_decision"],
};
const ROUTE_OF: Record<MissionType, RouteType> = { win_tender: "prime_bid", supply_winner: "supply_winner", client_bd: "client_bd", strategic_signal: "principal_trade" };

// Basis labels a claim may carry. A claim with a number must carry one of them.
export const BASIS = ["official-source-asserted", "counterparty-confirmed", "client-asserted", "deal-record", "quote", "benchmark", "confirmed", "assumption", "computed",
  "hypothesis", "supplier-index", "name-screening", "unknown"] as const;
export type Basis = (typeof BASIS)[number];
export type Claim = { text: string; source: string; basis: string; value?: number | null };
export type Stop = { status: "needs_owner" | "waiting_on_external" | "paused_on_risk"; question: string };
export type TaskOutput = { step: StepId; version: string; at: string; summary: string; claims: Claim[]; sources: string[]; open_questions: string[]; stop: Stop | null; data: Record<string, unknown> };

/** What the runner knows about the mission's deal. Loaded by deps.context on every step, never cached. */
export type RunContext = {
  now: string;                       // ISO, from the caller's clock
  records: DealRecord[];             // the deal file
  tender: { stage: string; deadline: string; buyer: string; title: string; link: string } | null; // the notice with the deal's id, if any
  award: { winner: string; source: string; date: string } | null;                                // the award of that notice, if indexed
  comparison: QuoteComparison;       // lib/quotes.ts compareQuotes, when the deal has quotes
};
export type Candidate = { name: string; country: string; match: MatchResult };
export type RunDeps = Ctx & {
  workspace: string;
  context: (m: Mission) => Promise<RunContext>;
  /** Supplier candidates for an English product phrase, already classified by lib/supmatch.ts. null: the index could not be read. */
  suppliers: (query: string) => Promise<Candidate[] | null>;
  screen: (parties: ScreenParty[], now: string) => Promise<PartyScreen>;
};

const s = (v: unknown) => String(v ?? "").trim();
const key = (v: unknown) => s(v).toLowerCase();
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const cut = (v: unknown, n: number) => s(v).replace(/\s+/g, " ").slice(0, n);
const taskKey = (m: Pick<Mission, "id">, step: StepId) => `${m.id}:${step}`;
export const stepOf = (t: Pick<MissionTask, "idempotency_key">): StepId | null => { const x = t.idempotency_key.split(":").pop() as StepId; return STEPS.includes(x) ? x : null; };
const host = (link: string) => { try { return new URL(link).hostname.toLowerCase().replace(/^www\./, ""); } catch { return ""; } };
function live(records: DealRecord[]): DealRecord[] {
  const latest = new Map<string, DealRecord>();
  for (const r of records) { const k = `${r.kind}|${r.record_id}`, p = latest.get(k); if (!p || r.version >= p.version) latest.set(k, r); }
  return [...latest.values()].filter((r) => r.status !== "deleted");
}

const QUESTION: Record<StepId, string> = {
  award_verification: "Is the award published at its source, and who is the named winner?",
  notice_verification: "Is the notice published at its source, open, and what is its deadline?",
  signal_verification: "What is the source of this signal?",
  prospect_verification: "Who is the prospect, and what source names it?",
  requirements_reading: "Which requirements does the deal file record for this tender, and which mandatory ones are not evidenced?",
  procurement_hypothesis: "What may the winner still have to buy to deliver the award? (a hypothesis, not confirmed demand)",
  demand_hypothesis: "What may the buyer need? (a hypothesis, not confirmed demand)",
  supplier_match: "Which suppliers in the index match the requested product, and how strong is the evidence?",
  sanctions_screen: "Do the buyer, winner and supplier names have a candidate match on the sanctions lists?",
  economics: "What do the recorded quotes and economics inputs give, and which inputs are unknown?",
  route_evaluation: "Which state do the gates give this route, and what blocks it?",
  independent_review: "Does every claim have a source, every number a basis label, and is the state no higher than the gates allow?",
  owner_decision: "What is the next decision for the owner?",
};

/** The task list of a mission: one task per step, each depending on the one before it, with a stable idempotency key. Pure. */
export function planMission(mission: Pick<Mission, "id" | "type" | "deal_id">, context?: Partial<RunContext> | null): TaskInput[] {
  const steps = PLANS[mission.type] || [];
  const about = cut(context?.tender?.title, 120) || (mission.deal_id ? `deal ${mission.deal_id}` : "");
  return steps.map((step, i) => ({ idempotency_key: taskKey(mission, step), role: STEP_ROLE[step], question: `${QUESTION[step]}${about ? ` [${about}]` : ""}`,
    depends_on: i ? [taskKey(mission, steps[i - 1])] : [], max_attempts: 3, cost_reservation_usd: 0 }));
}

// ---- assertions (the red team's rules; also the per-task review) ----------------------------------------------------
export type Finding = { task: string; rule: "no_source" | "no_basis" | "empty" | "hypothesis_label" | "state_above_gates" | "sanctions_not_reflected"; detail: string };
const HYPOTHESIS: StepId[] = ["procurement_hypothesis", "demand_hypothesis"];
const hasNumber = (c: Claim) => typeof c.value === "number" || /\d/.test(String(c.text || ""));

/** Rules over one output: every claim has a source; no number without a basis label; a hypothesis says "not confirmed demand". */
export function reviewOutput(task: string, o: TaskOutput | null | undefined): Finding[] {
  const f: Finding[] = [];
  if (!o || !Array.isArray(o.claims) || !o.claims.length) return [{ task, rule: "empty", detail: "the output has no claim" }];
  o.claims.forEach((c, i) => {
    const label = `claim ${i + 1} "${cut(c?.text, 80)}"`;
    if (!s(c?.text)) f.push({ task, rule: "empty", detail: `claim ${i + 1} has no text` });
    if (!s(c?.source)) f.push({ task, rule: "no_source", detail: `${label} has no source` });
    if (hasNumber(c) && !(BASIS as readonly string[]).includes(s(c?.basis))) f.push({ task, rule: "no_basis", detail: `${label} states a number without a basis label` });
  });
  if (HYPOTHESIS.includes(o.step) && !/not confirmed demand/i.test(o.summary || "")) f.push({ task, rule: "hypothesis_label", detail: "a hypothesis must say \"not confirmed demand\"" });
  return f;
}

const outputOf = (m: Mission, step: StepId): TaskOutput | null => { const t = m.tasks.find((x) => stepOf(x) === step); return t && t.status === "completed" && t.output ? (t.output as TaskOutput) : null; };

/** The independent review: reviewOutput over every other completed output, then the cross checks. Pure. */
export function redTeam(m: Mission): { verdict: "pass" | "fail"; findings: Finding[]; checked: string[]; claims_checked: number } {
  const others = m.tasks.filter((t) => t.status === "completed" && stepOf(t) !== "independent_review" && stepOf(t) !== "owner_decision");
  const findings: Finding[] = []; let claims = 0;
  for (const t of others) { const o = t.output as TaskOutput | null; claims += o?.claims?.length || 0; findings.push(...reviewOutput(t.idempotency_key, o)); }
  const routeTask = others.find((t) => stepOf(t) === "route_evaluation"), ro = routeTask?.output as TaskOutput | undefined;
  if (routeTask && ro) {
    const claimed = s(ro.data?.state) as RouteState, route = ro.data?.route as OpportunityRoute | undefined;
    let allowed: RouteState | null = null;
    try { allowed = route ? evaluateRoute(route).state : null; } catch { allowed = null; }
    if (!allowed || !STATES.includes(claimed)) findings.push({ task: routeTask.idempotency_key, rule: "state_above_gates", detail: `the state "${claimed}" cannot be checked against the gates: the stored route is unreadable` });
    else if (STATE_RANK[claimed] < STATE_RANK[allowed]) findings.push({ task: routeTask.idempotency_key, rule: "state_above_gates", detail: `the output states ${claimed}; the gates allow no more than ${allowed}` });
    else if (claimed !== allowed) findings.push({ task: routeTask.idempotency_key, rule: "state_above_gates", detail: `the output states ${claimed}; the gates give ${allowed}` });
    const screen = outputOf(m, "sanctions_screen");
    if (screen?.data?.status === "FAILED" && route && route.authority?.sanctions_alert !== true) findings.push({ task: routeTask.idempotency_key, rule: "sanctions_not_reflected", detail: "a sanctions candidate match is recorded, but the route carries no sanctions alert" });
  }
  return { verdict: findings.length ? "fail" : "pass", findings, checked: others.map((t) => t.idempotency_key), claims_checked: claims };
}

// ---- step executors -------------------------------------------------------------------------------------------------
type StepResult = { kind: "blocked"; stop: Stop } | { kind: "done"; output: TaskOutput };
const blocked = (status: Stop["status"], question: string): StepResult => ({ kind: "blocked", stop: { status, question } });
type Env = { m: Mission; c: RunContext; deps: RunDeps; step: StepId };
function done(e: Env, summary: string, claims: Claim[], data: Record<string, unknown> = {}, open: string[] = [], stop: Stop | null = null): StepResult {
  const cl = claims.map((c) => ({ text: cut(c.text, 400), source: cut(c.source, 300), basis: s(c.basis), ...(c.value === undefined ? {} : { value: c.value }) }));
  return { kind: "done", output: { step: e.step, version: RUN_VERSION, at: e.c.now, summary: cut(summary, 600), claims: cl, sources: [...new Set(cl.map((c) => c.source).filter(Boolean))],
    open_questions: open.map((q) => cut(q, 300)), stop, data } };
}

function facts(e: Env) {
  const r = live(e.c.records), t = e.c.tender, deal = e.m.deal_id;
  const stage = r.find((x) => x.kind === "stage")?.data || {};
  const buyerParty = r.find((x) => x.kind === "party" && x.data.role === "buyer" && s(x.data.status || x.status) !== "dropped");
  const quotes = r.filter((x) => x.kind === "quote");
  return { r, t, deal, stage, buyerParty, buyer: s(buyerParty?.data.name) || s(t?.buyer), spec: s(stage.title) || s(t?.title) || s(quotes[0]?.data.product), quotes,
    reqs: r.filter((x) => x.kind === "requirement"), econ: r.find((x) => x.kind === "economics")?.data || null, chosen: chooseSupplier(e.c.records) };
}
const noNotice = (deal: string, what: string) => `No notice with the id "${deal}" is in the tender index, so ${what} cannot be read from a source. Which official notice (link) is this mission about? Open the mission on the deal whose id is the notice id, or cancel it.`;

function verify(e: Env): StepResult {
  const f = facts(e), t = f.t, st = key(t?.stage);
  if (!f.deal) return blocked("needs_owner", "This mission has no deal. Which deal (notice id) is it about? Create the mission from that deal's page.");
  const noticeClaims = (): Claim[] => [
    { text: `Buyer: ${s(t!.buyer) || "not stated in the notice"}`, source: t!.link, basis: "official-source-asserted" },
    { text: `Subject: ${s(t!.title) || "not stated in the notice"}`, source: t!.link, basis: "official-source-asserted" },
    { text: `Stage at the source index: ${st || "unknown"}${s(t!.deadline) ? `; deadline ${s(t!.deadline).slice(0, 10)}` : "; no deadline stated"}`, source: t!.link, basis: "official-source-asserted" }];
  if (e.step === "prospect_verification") {
    const p = f.buyerParty;
    if (p && s(p.data.source)) return done(e, `Prospect ${s(p.data.name)}, as recorded on the deal with its source.`, [{ text: `Prospect: ${s(p.data.name)}${s(p.data.country) ? ` (${s(p.data.country)})` : ""}`, source: s(p.data.source), basis: "client-asserted" }], { prospect: s(p.data.name) });
    if (t && s(t.link) && s(t.buyer)) return done(e, `Prospect ${s(t.buyer)}, the buyer named in the notice.`, noticeClaims(), { prospect: s(t.buyer) });
    return blocked("needs_owner", p ? `The buyer "${s(p.data.name)}" on deal ${f.deal} has no source. Which page, document or notice names it? Add it to the party record.`
      : `Which buyer is this client development mission about? Deal ${f.deal} has no buyer party and no notice. Add the buyer as a party with its source.`);
  }
  if (!t) return blocked("needs_owner", noNotice(f.deal, e.step === "award_verification" ? "the award" : e.step === "signal_verification" ? "the signal" : "the tender"));
  if (!s(t.link)) return blocked("needs_owner", `The notice "${f.deal}" has no link in the tender index. What is its official source (link)?`);
  if (e.step === "signal_verification") return done(e, `Signal read from the notice "${cut(t.title, 120)}" (${st || "stage unknown"}).`, noticeClaims(), { stage: st });
  if (e.step === "notice_verification") {
    if (st === "planned") return blocked("waiting_on_external", `The procurement "${cut(t.title, 120)}" is announced but not open. Has ${s(t.buyer) || "the buyer"} published the tender? (${t.link})`);
    if (st === "tender" || st === "open") return done(e, `The notice is published and open${s(t.deadline) ? `, deadline ${s(t.deadline).slice(0, 10)}` : ", with no deadline stated"}.`, noticeClaims(), { stage: st },
      s(t.deadline) ? [] : ["What is the bid deadline? The notice in the index states none."]);
    return done(e, `The notice is ${st || "at an unknown stage"}: a prime bid cannot be confirmed as open.`, noticeClaims(), { stage: st }, [],
      { status: "needs_owner", question: `The notice "${f.deal}" is ${st || "at an unknown stage"} in the index, not open. Is a prime bid still possible? If not, cancel this mission or open a "supply the winner" mission.` });
  }
  // award_verification
  if (st !== "awarded") return blocked(st === "closed" || st === "cancelled" ? "needs_owner" : "waiting_on_external",
    st === "closed" || st === "cancelled" ? `The notice "${f.deal}" is ${st} in the index and no award is recorded. Was it awarded, and to whom (name and link of the award notice)?`
      : `The notice "${f.deal}" is at stage "${st || "unknown"}": no award is published. Has the award been published, and who won? (${t.link})`);
  const a = e.c.award;
  if (!a || !s(a.winner)) return blocked("needs_owner", `The notice "${f.deal}" is marked awarded, but the awards index names no winner for it. Who won (the name as written in the award notice, with its link)?`);
  // the winner claim carries the award's own source as given: a missing source is not replaced, the review finds it
  return done(e, `Award verified at the source index: ${s(a.winner)} won "${cut(t.title, 120)}" from ${s(t.buyer) || "the buyer"}.`,
    [...noticeClaims(), { text: `Winner: ${s(a.winner)}${s(a.date) ? ` (award dated ${s(a.date).slice(0, 10)})` : ""}`, source: s(a.source), basis: "official-source-asserted" }],
    { winner: s(a.winner), award_source: s(a.source), award_date: s(a.date), stage: st });
}

function requirementsReading(e: Env): StepResult {
  const f = facts(e);
  if (!f.reqs.length) return blocked("needs_owner", `No requirement is recorded on deal ${f.deal}. Reading the tender documents needs a person or a model, which this runner does not use. Which mandatory requirements does the tender state (product, grade, quantity, standard, documents)? Record them on the deal.`);
  const st = (x: DealRecord) => s(x.data.status || x.status) || "unknown";
  const claims = f.reqs.slice(0, 25).map((x): Claim => ({ text: `${x.data.mandatory !== false ? "Mandatory" : "Optional"} requirement "${cut(x.data.item, 160)}": ${st(x)}`,
    source: s(x.data.source_doc) || s(x.data.evidence) || `deal ${f.deal} requirement ${x.record_id}`, basis: "deal-record" }));
  const open = f.reqs.filter((x) => x.data.mandatory !== false && st(x) !== "met" && st(x) !== "not_met").map((x) => `Does the supplier's evidence state the mandatory requirement "${cut(x.data.item, 160)}"?`);
  return done(e, `${f.reqs.length} requirement(s) on the deal file; ${open.length} mandatory one(s) not evidenced. The tender documents themselves were not read by this runner.`, claims, { requirements: f.reqs.length, not_evidenced: open.length }, open);
}

function hypothesis(e: Env): StepResult {
  const f = facts(e);
  if (!f.spec) return blocked("needs_owner", `What product does this mission concern? Deal ${f.deal} has no title on its stage record and no notice title. Record the product as the deal's title.`);
  if (e.step === "procurement_hypothesis") {
    const award = outputOf(e.m, "award_verification"), winner = s(award?.data.winner), src = s(award?.data.award_source) || s(f.t?.link);
    const text = `Hypothesis, not confirmed demand: ${winner || "the winner"} may still have to buy "${cut(f.spec, 160)}" to deliver the award of ${f.buyer || "the buyer"}. No source shows that ${winner || "the winner"} has asked for it or has not already contracted it.`;
    return done(e, text, [{ text, source: src, basis: "hypothesis" }], { winner, product: f.spec, confirmed: false },
      [`Has ${winner || "the winner"} already contracted its supply of "${cut(f.spec, 120)}"? Only ${winner || "the winner"} can confirm; asking needs a message approved by the owner.`]);
  }
  const first = outputOf(e.m, e.m.type === "client_bd" ? "prospect_verification" : "signal_verification");
  const who = s(first?.data.prospect) || f.buyer || "the buyer";
  const text = `Hypothesis, not confirmed demand: ${who} may need "${cut(f.spec, 160)}". No source shows a request from ${who} to this organisation.`;
  return done(e, text, [{ text, source: s(first?.sources?.[0]) || s(f.t?.link), basis: "hypothesis" }], { buyer: who, product: f.spec, confirmed: false },
    [`Does ${who} have an open need for "${cut(f.spec, 120)}", in what quantity and by when? Only ${who} can confirm; asking needs a message approved by the owner.`]);
}

async function supplierMatch(e: Env): Promise<StepResult> {
  const f = facts(e), query = cut(f.spec, 160);
  if (!query) return blocked("needs_owner", `Which product should suppliers be matched to? Deal ${f.deal} has no title on its stage record and no notice title. Record the product as the deal's title.`);
  if (/[^\u0000-ɏ]/.test(query)) return blocked("needs_owner", `The product name "${cut(query, 80)}" is not in Latin script. Matching it needs a translation (a model call), which this runner does not make. What is the product in English? Record it as the deal's title.`);
  const found = await e.deps.suppliers(query);
  if (!found) return blocked("waiting_on_external", `The supplier index could not be read, so no match was run for "${query}". Run the step again when the index answers.`);
  const cands = found.filter((x) => s(x.name) && x.match && x.match.bucket !== "incompatible").map((x, i) => ({ x, i })).sort((a, b) => BUCKET_RANK[a.x.match.bucket] - BUCKET_RANK[b.x.match.bucket] || a.i - b.i).slice(0, 8).map((y) => y.x);
  const src = `supplier index, ${MATCH_VERSION}`;
  const same = f.chosen.supplier ? cands.find((x) => key(x.name) === key(f.chosen.supplier)) : undefined;
  const proposed = f.chosen.supplier ? { name: f.chosen.supplier, fit: (same?.match.bucket || "unknown") as TechnicalFit, basis: `deal file: ${f.chosen.basis}` }
    : cands[0] ? { name: cands[0].name, fit: cands[0].match.bucket as TechnicalFit, basis: "first candidate of the index match; selected by nobody" } : null;
  const claims: Claim[] = cands.map((x) => ({ text: `${x.name}${s(x.country) ? ` (${s(x.country)})` : ""}: ${x.match.bucket}. ${cut(x.match.why, 200)}${x.match.gaps?.length ? ` Gaps: ${cut(x.match.gaps.join("; "), 160)}` : ""}`,
    source: s(x.match.url) || src, basis: "supplier-index" }));
  if (f.chosen.supplier) claims.unshift({ text: `Supplier on the deal file: ${f.chosen.supplier} (${f.chosen.basis}); index match for this product: ${same ? same.match.bucket : "not found in the index"}`, source: `deal ${f.deal} records; ${src}`, basis: "deal-record" });
  if (!claims.length) claims.push({ text: `No candidate found in the supplier index for "${query}"`, source: src, basis: "supplier-index" });
  const open = !proposed ? [`Which supplier can make exactly "${query}"? The index returned no candidate.`]
    : proposed.fit !== "supported" ? [`Is there product evidence that ${proposed.name} makes exactly "${query}"? The index match is "${proposed.fit}".`] : [];
  return done(e, proposed ? `${cands.length} candidate(s) for "${query}"; carried forward: ${proposed.name} (fit ${proposed.fit}; ${proposed.basis}). An index match is evidence to check, not a confirmed capability.`
    : `No supplier candidate for "${query}" in the index.`, claims,
    { query, match_version: MATCH_VERSION, proposed, candidates: cands.map((x) => ({ name: x.name, country: s(x.country), bucket: x.match.bucket, evidence: cut(x.match.evidence, 80), url: s(x.match.url) })) }, open);
}

async function sanctionsScreen(e: Env): Promise<StepResult> {
  const f = facts(e), parties: ScreenParty[] = dealParties(e.c.records, { tender: e.c.tender });
  const winner = s(outputOf(e.m, "award_verification")?.data.winner), prospect = s(outputOf(e.m, "prospect_verification")?.data.prospect);
  const proposed = (outputOf(e.m, "supplier_match")?.data.proposed || null) as { name: string } | null;
  if (winner) parties.push({ role: "winner", name: winner });
  if (prospect) parties.push({ role: "buyer", name: prospect });
  if (proposed?.name) parties.push({ role: "supplier", name: proposed.name });
  if (!parties.length) return blocked("needs_owner", `No buyer, winner or supplier is named on deal ${f.deal}, so there is no name to screen. Who are the parties? Add them to the deal.`);
  const sc = await e.deps.screen(parties, e.c.now);
  const names = (sc.screened.length ? sc.screened : parties).map((p) => p.name).join("; ");
  if (sc.status === "NOT_CHECKED" || sc.status === "STALE") return blocked("waiting_on_external", `Sanctions screen ${sc.status}: ${sc.label}. The names (${cut(names, 300)}) are not screened; nothing continues on an unscreened route. Run the step again when the sanctions index is readable and current.`);
  const src = `${SANCTIONS_SOURCE}, index updated ${sc.index_updated || "unknown"}`;
  const data = { status: sc.status, label: sc.label, checked_on: sc.checked_on, index_updated: sc.index_updated, screened: sc.screened, candidates: sc.candidates.slice(0, 20), clearance: false };
  if (sc.status === "FAILED") {
    const hit = [...new Set(sc.candidates.map((c) => c.name))].join("; ");
    return done(e, `FAILED: sanctions candidate match for ${hit}. Qualified review required. Name matching only: a candidate is a lead to verify, not a verdict, and it is never cleared automatically.`,
      sc.candidates.slice(0, 20).map((c) => ({ text: `${c.role} "${c.name}": ${c.strength} with "${c.matched}" on ${c.list}${c.program ? `, program ${c.program}` : ""} (ref ${c.ref})`, source: src, basis: "name-screening" })), data, [],
      { status: "paused_on_risk", question: `qualified review required: sanctions candidate match for ${cut(hit, 200)} (${sc.candidates.length} candidate(s), name matching only). The mission does not continue; the alert is never cleared automatically.` });
  }
  if (sc.status !== "CHECKED_NO_ISSUE") return blocked("needs_owner", `The sanctions screen returned the status ${sc.status}, which this runner does not produce or accept. Who verified the parties, and where is that review recorded?`);
  return done(e, `CHECKED_NO_ISSUE: checked, no candidate match on ${sc.checked_on} for ${cut(names, 300)}. Name matching only; this is not a clearance.`,
    [{ text: `Checked, no candidate match on ${sc.checked_on} for: ${cut(names, 300)}. Name matching only; not a clearance`, source: src, basis: "name-screening" }], data);
}

function economics(e: Env): StepResult {
  const f = facts(e), x = f.econ || {}, deal = f.deal, src = `deal ${deal} economics record (entered as assumptions)`;
  const LABEL: Record<string, string> = { sale_price: "sale price", cost_goods: "cost of goods", freight: "freight", insurance: "insurance", inspection: "inspection", funding_limit: "funding limit",
    fin_rate_pct: "financing rate (% a year)", balance_day: "day the supplier is paid", customer_day: "day the customer pays" };
  const inputs: Record<string, number | null> = {};
  for (const k of Object.keys(LABEL)) inputs[k] = num(x[k]);
  const claims: Claim[] = [], open: string[] = [];
  for (const [k, v] of Object.entries(inputs)) if (v !== null) claims.push({ text: `${LABEL[k]}: ${v}`, value: v, source: src, basis: "assumption" });
  // the quotes on the deal, as lib/quotes.ts compared them; nothing is converted here
  const rows = (e.c.comparison?.groups || []).flatMap((g) => g.rows.map((r) => ({ group: g.basis, ...r }))).slice(0, 8);
  for (const r of rows) {
    const rec = f.quotes.find((q) => key(q.data.supplier) === key(r.supplier));
    claims.push({ text: `Quote from ${r.supplier}: ${r.price === null ? "no price" : `${r.price} ${r.currency}/${r.unit || "unit"}`}${r.usd === null ? "" : `, ${r.usd} ${r.basis}`} (${r.group}${r.flags.length ? `; flags: ${r.flags.join(", ")}` : ""})`,
      value: r.price, source: s(rec?.data.source_ref) || `deal ${deal} quote record`, basis: "quote" });
  }
  if (f.quotes.length && !rows.length) open.push(`The ${f.quotes.length} quote(s) on deal ${deal} could not be compared now (the comparison did not answer). Run the step again.`);
  const sale = inputs.sale_price, goods = inputs.cost_goods;
  const extras = [x.freight_in_quote === true ? null : inputs.freight, x.insurance_in_quote === true ? null : inputs.insurance, inputs.inspection];
  const cost = goods === null ? null : extras.reduce<number>((sum, v) => sum + (v ?? 0), goods);
  const margin = sale !== null && cost !== null ? sale - cost : null;
  if (margin !== null) claims.push({ text: `Margin before financing: ${margin} (sale price ${sale} less stated absolute costs ${cost}; percentage items are not applied)`, value: margin, source: `computed from ${src}`, basis: "computed" });
  // cash check only when every one of its inputs is recorded: a missing day or rate is never replaced by a default
  let cash: ReturnType<typeof cashCheck> | null = null;
  if (sale !== null && cost !== null && inputs.balance_day !== null && inputs.customer_day !== null && inputs.fin_rate_pct !== null) {
    cash = cashCheck([{ day: inputs.balance_day, amount: -cost }, { day: inputs.customer_day, amount: sale }], inputs.fin_rate_pct / 100, inputs.funding_limit);
    claims.push({ text: `Peak funding ${Math.round(cash.peak_funding)}, financing cost ${Math.round(cash.finance_cost)}, funding capacity: ${cash.funding_capacity}`, value: Math.round(cash.peak_funding),
      source: `computed by lib/dealstate.ts cashCheck from ${src}`, basis: "computed" });
  }
  const unknown = Object.keys(LABEL).filter((k) => inputs[k] === null && !(k === "freight" && x.freight_in_quote === true) && !(k === "insurance" && x.insurance_in_quote === true));
  for (const k of unknown) open.push(`What is the ${LABEL[k]}? It is not recorded in the economics of deal ${deal}.`);
  if (!rows.some((r) => r.price !== null)) open.push("What is the supplier's actual quoted price? No priced quote is recorded; a request for quotation needs the owner's approval.");
  if (!claims.length) claims.push({ text: `No economics record and no quote on deal ${deal}: every finance number is unknown`, source: `deal ${deal} records`, basis: "unknown" });
  return done(e, `Economics: margin ${margin === null ? "unknown" : margin}, peak funding ${cash ? Math.round(cash.peak_funding) : "unknown"}. ${unknown.length ? `Unknown, not assumed: ${unknown.map((k) => LABEL[k]).join(", ")}.` : "Every input is recorded."} Inputs from the economics record are assumptions; this is not a profit statement.`,
    claims, { inputs, cost, margin, peak_funding: cash ? cash.peak_funding : null, finance_cost: cash ? cash.finance_cost : null, funding_capacity: cash ? cash.funding_capacity : "unknown", unknown,
      quotes: rows.map((r) => ({ supplier: r.supplier, group: r.group, usd: r.usd, basis: r.basis, rank: r.rank, flags: r.flags })) }, open);
}

/** The route this mission evaluates: the deal-file mapping (lib/routemap.ts), then what the earlier tasks established. */
export function missionRoute(m: Mission, c: RunContext): OpportunityRoute {
  const screen = outputOf(m, "sanctions_screen"), match = outputOf(m, "supplier_match"), award = outputOf(m, "award_verification"), econ = outputOf(m, "economics");
  const ctx: DealContext = { deal_id: m.deal_id, workspace: m.workspace, tender: c.tender, sanctions: null };
  const route = routeFromDeal(c.records, c.comparison, c.now, ctx), type = ROUTE_OF[m.type];
  route.id = `${m.id}:${type}`; route.route_type = type;
  // a recorded candidate match keeps the alert for the life of the mission, whatever a later screen would say
  route.authority.sanctions_alert = screen?.data.status === "FAILED";
  const proposed = (match?.data.proposed || null) as { name: string; fit: TechnicalFit } | null;
  if (proposed?.name && (!route.supply.supplier || key(route.supply.supplier) === key(proposed.name))) {
    if (!route.supply.supplier) route.supply.supplier = proposed.name;
    if (route.supply.technical_fit === "unknown") route.supply.technical_fit = proposed.fit; // the checklist's "supported" is kept; the index never lowers or raises it
  }
  if (award) {
    route.demand.status = "awarded";
    const item: EvidenceItem = { claim: `award to ${s(award.data.winner)}`, source_family: host(s(award.data.award_source)) || "award-notice", status: "official-source-asserted", retrieved_at: c.now.slice(0, 10), valid_until: null };
    route.evidence.push(item);
  }
  const peak = num(econ?.data.peak_funding);
  if (peak !== null) route.economics.capital_need = peak;
  return route;
}

function routeEvaluation(e: Env): StepResult {
  const route = missionRoute(e.m, e.c), ev = evaluateRoute(route);
  const src = `lib/route.ts evaluateRoute over deal ${e.m.deal_id} and this mission's task outputs`;
  const claims: Claim[] = [{ text: `Route state: ${ev.state} (${ev.route_type})`, source: src, basis: "computed" },
    ...ev.blockers.slice(0, 6).map((b): Claim => ({ text: `${b.decisive ? "Blocker" : "Limit"} (${b.gate}): ${b.text}`, source: src, basis: "computed" }))];
  return done(e, `Route state ${ev.state} for ${ev.route_type}. ${ev.blockers[0] ? `First ${ev.blockers[0].decisive ? "blocker" : "limit"}: ${ev.blockers[0].text}.` : "No blocker."} Set by fixed gates, not by a score; this is not a likelihood of winning.`,
    claims, { route, state: ev.state, route_type: ev.route_type, blockers: ev.blockers.slice(0, 8), missing: ev.missing.slice(0, 10).map((x) => ({ gate: x.gate, question: x.question, why: x.why })), next_task: ev.next_task,
      profit_statement: ev.profit_statement, source_families: ev.source_families, exact_fit: ev.exact_fit, days_left: ev.days_left },
    ev.next_task ? [ev.next_task.question] : []);
}

function independentReview(e: Env): StepResult {
  const r = redTeam(e.m), src = `outputs of ${r.checked.length} task(s): ${r.checked.map((k) => k.split(":").pop()).join(", ")}`;
  const claims: Claim[] = [{ text: `Checked ${r.checked.length} output(s) and ${r.claims_checked} claim(s): ${r.findings.length} finding(s)`, value: r.findings.length, source: src, basis: "computed" },
    ...r.findings.slice(0, 20).map((f): Claim => ({ text: `${f.rule} in ${f.task.split(":").pop()}: ${f.detail}`, source: f.task, basis: "computed" }))];
  const list = r.findings.slice(0, 4).map((f) => `${f.task.split(":").pop()}: ${f.detail}`).join(" | ");
  return done(e, r.verdict === "pass" ? `Independent review passed: every claim has a source, every number a basis label, and the state is what the gates give. ${r.claims_checked} claim(s) in ${r.checked.length} output(s).`
    : `Independent review FAILED with ${r.findings.length} finding(s): ${list}`, claims, { verdict: r.verdict, findings: r.findings.slice(0, 40), checked: r.checked, claims_checked: r.claims_checked }, [],
    r.verdict === "fail" ? { status: "needs_owner", question: `The red team found ${r.findings.length} problem(s) in this mission's outputs: ${cut(list, 500)}. Which source backs each one? Until they are answered no recommendation is made.` } : null);
}

function ownerDecision(e: Env): StepResult {
  const review = outputOf(e.m, "independent_review"), route = outputOf(e.m, "route_evaluation"), screen = outputOf(e.m, "sanctions_screen");
  if (review?.data.verdict !== "pass") return blocked("needs_owner", `No recommendation: the independent review ${review ? "failed" : "is missing"}. ${cut(review?.summary, 500)}`);
  const open = e.m.tasks.flatMap((t) => (t.status === "completed" ? ((t.output as TaskOutput | null)?.open_questions || []) : []));
  const uniq = [...new Set(open)];
  const state = s(route?.data.state), next = route?.data.next_task as { question: string } | null | undefined;
  const ASK: Record<string, string> = {
    READY_FOR_OWNER_REVIEW: "The checks this runner can make are done. Do you approve a first message to the counterparty? Each outgoing message still needs your approval.",
    READY_FOR_AUTHORIZED_CONTACT: "The gates pass and an approval is on file. Do you want the next message drafted for your approval?",
    ACTIVE: "Contact is recorded. What is the next move with the counterparty?",
    STOPPED: "The route is stopped (sanctions alert or owner stop). Qualified review is required before anything else.",
    INELIGIBLE: "This route cannot be used. Cancel the mission, or open one for another route type?",
    MISMATCH: "The supplier's evidence contradicts a mandatory requirement. Drop this supplier or cancel?",
  };
  const ask = !route ? "This is a hypothesis, not confirmed demand. Do you want a deal mission opened for it (win a tender, supply the winner or client development)?"
    : ASK[state] || `The route is in ${state}. ${next ? `The cheapest open question: ${next.question}` : ""} Who answers it?`;
  const text = `${route ? `Route state ${state}. ` : ""}${ask}${screen ? ` Sanctions: ${s(screen.data.status)} (${screen.data.status === "FAILED" ? "qualified review required" : "name screen only, not a clearance"}).` : " Sanctions: NOT_CHECKED in this mission."}${uniq.length ? ` Open questions (${uniq.length}): ${uniq.slice(0, 4).join(" | ")}` : ""}`;
  const keys = e.m.tasks.filter((t) => t.status === "completed").map((t) => t.idempotency_key.split(":").pop()).join(", ");
  return done(e, text, [{ text, source: `this mission's task outputs: ${keys}`, basis: "computed" }], { state: state || null, open_questions: uniq }, uniq);
}

async function execute(e: Env): Promise<StepResult> {
  switch (e.step) {
    case "award_verification": case "notice_verification": case "signal_verification": case "prospect_verification": return verify(e);
    case "requirements_reading": return requirementsReading(e);
    case "procurement_hypothesis": case "demand_hypothesis": return hypothesis(e);
    case "supplier_match": return supplierMatch(e);
    case "sanctions_screen": return sanctionsScreen(e);
    case "economics": return economics(e);
    case "route_evaluation": return routeEvaluation(e);
    case "independent_review": return independentReview(e);
    case "owner_decision": return ownerDecision(e);
  }
}

// ---- the runner -----------------------------------------------------------------------------------------------------
export type RunResult = { ok: boolean; mission: Mission | null; ran: string | null; note: string; error?: string };

async function applyStop(deps: RunDeps, id: string, stop: Stop): Promise<void> {
  if (stop.status === "paused_on_risk") await pause(deps, deps.workspace, id, stop.question);
  else if (stop.status === "waiting_on_external") { const r = await waitOnExternal(deps, deps.workspace, id, stop.question); if (!r.ok) await needOwner(deps, deps.workspace, id, stop.question); }
  else await needOwner(deps, deps.workspace, id, stop.question);
}

/** The reviewer role's check of one completed task, and what follows from it. Used right after completion and after a restart. */
async function reviewAndStop(deps: RunDeps, id: string, t: MissionTask): Promise<string> {
  const o = t.output as TaskOutput | null, step = stepOf(t);
  if (step === "owner_decision") { await needOwner(deps, deps.workspace, id, o?.summary || "decision needed"); return "the decision waits for the owner"; }
  const findings = reviewOutput(t.idempotency_key, o);
  // the independent review is itself checked by source_evidence: it must have covered every other completed task
  if (step === "independent_review") {
    const m = await loadMission(deps, deps.workspace, id), covered = new Set((o?.data.checked as string[] | undefined) || []);
    for (const x of m?.tasks || []) if (x.status === "completed" && stepOf(x) !== "independent_review" && stepOf(x) !== "owner_decision" && !covered.has(x.idempotency_key))
      findings.push({ task: t.idempotency_key, rule: "empty", detail: `the review did not cover ${x.idempotency_key}` });
  }
  const verdict = findings.length ? "fail" : "pass", notes = findings.length ? findings.slice(0, 5).map((f) => f.detail).join("; ") : "every claim has a source and every number a basis label";
  const r = await reviewTask(deps, deps.workspace, id, t.idempotency_key, { reviewer_role: reviewerFor(t.role), verdict, notes });
  if (!r.ok) return `review not recorded: ${r.error}`;
  if (verdict === "fail") {
    if (r.mission.status !== "failed") await needOwner(deps, deps.workspace, id, `The ${reviewerFor(t.role)} review of ${step} failed: ${cut(notes, 500)}. Which source backs it? Correct the record, then run the step again (attempt ${t.attempt} of ${t.max_attempts}).`);
    return `review failed: ${notes}`;
  }
  if (o?.stop) { await applyStop(deps, id, o.stop); return `reviewed; stopped at ${o.stop.status}`; }
  return "completed and reviewed";
}

/** Add the plan's tasks that the mission does not have yet. Idempotent: an existing key is never added twice. */
export async function ensurePlan(deps: RunDeps, id: string): Promise<Mission | null> {
  let m = await loadMission(deps, deps.workspace, id);
  if (!m) return null;
  const have = new Set(m.tasks.map((t) => t.idempotency_key));
  const todo = planMission(m).filter((t) => !have.has(t.idempotency_key));
  if (!todo.length || ["completed", "failed", "cancelled"].includes(m.status)) return m;
  for (const t of todo) await addTask(deps, deps.workspace, id, t);
  m = await loadMission(deps, deps.workspace, id);
  return m;
}

/**
 * Execute exactly one runnable task of a mission, or report why none ran. No loop: one call, one step.
 * - paused_on_risk is never resumed here: a risk pause stays until a qualified person acts outside this runner.
 * - needs_owner / waiting_on_external: the call is the person's "check again". The step that stopped re-reads its
 *   inputs; if the answer is still missing the same stop comes straight back and nothing is recorded.
 * - Restart safety: a task left running is executed again and completed once; a task completed but not reviewed is
 *   reviewed; a completed task is never executed again, so no output is written twice.
 */
export async function runNext(missionId: string, deps: RunDeps): Promise<RunResult> {
  const ws = deps.workspace;
  const planned = await ensurePlan(deps, missionId);
  if (!planned) return { ok: false, mission: null, ran: null, note: "", error: "mission not found" };
  let m: Mission = planned;
  const fresh = async (): Promise<Mission> => (await loadMission(deps, ws, missionId)) || m;
  if (["completed", "failed", "cancelled"].includes(m.status)) return { ok: true, mission: m, ran: null, note: `the mission is ${m.status}` };
  if (m.status === "paused_on_risk") return { ok: true, mission: m, ran: null, note: "paused on a risk: qualified review required; this runner never clears it" };
  const was = m.status, question = m.next_decision;
  if (m.status === "needs_owner" || m.status === "waiting_on_external") { const r = await resume(deps, ws, missionId); if (r.ok) m = r.mission; }

  // a task completed before a restart and never reviewed (the owner's decision is reviewed by the owner, not here)
  const unreviewed = m.tasks.find((t) => t.status === "completed" && !t.reviewer_result && stepOf(t) !== "owner_decision");
  if (unreviewed) { const note = await reviewAndStop(deps, missionId, unreviewed); return { ok: true, mission: await fresh(), ran: unreviewed.idempotency_key, note }; }

  const task = m.tasks.find((t) => t.status === "running") || nextRunnable(m).sort((a, b) => a.seq - b.seq)[0];
  if (!task) {
    const dec = m.tasks.find((t) => stepOf(t) === "owner_decision" && t.status === "completed");
    if (dec) { await needOwner(deps, ws, missionId, (dec.output as TaskOutput | null)?.summary || "decision needed"); return { ok: true, mission: await fresh(), ran: null, note: "every step is done: the decision waits for the owner" }; }
    // nothing can start (for example the budget decision is still open): put the earlier stop back as it was
    if (was === "needs_owner") await needOwner(deps, ws, missionId, question.replace(/^owner: /, ""));
    else if (was === "waiting_on_external") await waitOnExternal(deps, ws, missionId, question.replace(/^waiting: /, ""));
    return { ok: true, mission: await fresh(), ran: null, note: "no task can start" };
  }
  const step = stepOf(task);
  if (!step) return { ok: true, mission: m, ran: null, note: `task ${task.idempotency_key} is not a step of this runner` };

  let c: RunContext;
  try { c = await deps.context(m); }
  catch (x) {
    await applyStop(deps, missionId, { status: "waiting_on_external", question: `The deal file of ${m.deal_id || "this mission"} could not be read (${cut((x as Error)?.message || x, 160)}). Run the step again when it answers.` });
    return { ok: true, mission: await fresh(), ran: null, note: "the deal file could not be read" };
  }
  let res: StepResult, crash = "";
  try { res = await execute({ m, c, deps, step }); } catch (x) { crash = cut((x as Error)?.message || x, 300) || "step failed"; res = blocked("needs_owner", crash); }

  if (crash) {
    // an unexpected error in the step's own code: counted as an attempt, as lib/mission.ts does for any failed task
    const r = await reserveCost(deps, ws, missionId, task.idempotency_key);
    if (r.ok) await failTask(deps, ws, missionId, task.idempotency_key, crash, 0);
    return { ok: false, mission: await fresh(), ran: task.idempotency_key, note: "the step failed", error: crash };
  }
  if (res.kind === "blocked") {
    // nothing is recorded on the task: a task left running by a restart goes back to queued without an output
    if (task.status === "running") await failTask(deps, ws, missionId, task.idempotency_key, `stopped: ${res.stop.question}`, 0);
    const now = await fresh();
    if (now.status !== "failed") await applyStop(deps, missionId, res.stop);
    return { ok: true, mission: await fresh(), ran: null, note: `${step} did not run: ${res.stop.status}` };
  }
  // reserve (0 USD for a code task), record the output once, reconcile the cost (0), review
  const rv = await reserveCost(deps, ws, missionId, task.idempotency_key);
  if (!rv.ok) return { ok: true, mission: rv.mission, ran: null, note: `${step} did not start: ${rv.error}` };
  const done_ = await completeTask(deps, ws, missionId, task.idempotency_key, res.output, 0);
  if (!done_.ok) return { ok: false, mission: done_.mission, ran: task.idempotency_key, note: "", error: done_.error };
  const note = await reviewAndStop(deps, missionId, done_.task);
  return { ok: true, mission: await fresh(), ran: task.idempotency_key, note: `${step}: ${note}` };
}
