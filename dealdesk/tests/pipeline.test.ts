// The role pipeline (lib/pipeline.ts) with a scripted model and in-memory stores: separate runs per role, recorded
// hand-offs, the rule check on top of the checker, the rewrite limit, the budget stop, the flag, and the gate.
import { MemoryBudgetStore, type BudgetConfig } from "@/lib/agentbudget";
import { asDraft, cellsToHandoff, clip, combineVerdict, handoffToCells, MAX_INPUT_BYTES, MemoryHandoffStore, parseArtefact, pipelineOn, proposalFor, runCase, systemFor,
  type Handoff, type ModelCall, type OutreachCase, type PipelineDeps, type ReplyCase, type Verdict } from "@/lib/pipeline";
import { sheetFor } from "@/lib/sheets";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const cfg: BudgetConfig = { dayUsd: 1, totalUsd: 5, from: "2026-11-12", until: "2026-11-14" };
const NOW = Date.parse("2026-11-12T10:00:00Z");

type Call = { role: string; system: string; input: string; maxOutputTokens: number };
type Script = Record<string, (string | Error)[]>;
/** A model that answers from a script, one queue per role (the last entry repeats), and remembers what it was asked. */
function fake(script: Script) {
  const calls: Call[] = [];
  const model: ModelCall = async (a) => {
    calls.push(a);
    const q = script[a.role] || [];
    const next = q.length > 1 ? q.shift()! : q[0];
    if (next === undefined) throw new Error(`no script for ${a.role}`);
    if (next instanceof Error) throw next;
    return { text: next, usage: { input_tokens: 800, output_tokens: 200 } };
  };
  return { model, calls };
}
function world(script: Script, over: Partial<PipelineDeps> = {}) {
  const f = fake(script), budget = new MemoryBudgetStore(), handoffs = new MemoryHandoffStore();
  const deps: PipelineDeps = { model: f.model, budget, handoffs, now: () => NOW, modelName: "scripted", budgetConfig: cfg, ...over };
  return { ...f, budget, handoffs, deps };
}
const NOTE = JSON.stringify({ counterparty: "Harbin Coil Works", facts: [
  { text: "Lists 304 and 316L stainless coil up to 1,500 mm wide", source: "https://example.com/products", date: "2026-11-10" },
  { text: "Exports to Kenya and Tanzania", source: "https://example.com/markets", date: "2026-11-10" }],
  reason_now: "a water utility contract in Kenya was awarded last week", unknown: ["minimum order quantity"], contact: "sales@example.com" });
const DRAFT = JSON.stringify({ subject: "Stainless coil for East Africa", sentences: [
  { text: "Dear Sales Team,", rests_on: "courtesy" },
  { text: "Your site lists 304 and 316L coil up to 1,500 mm wide.", rests_on: "note:1" },
  { text: "Do you supply this range to Kenya?", rests_on: "question" }] });
const BIO_DRAFT = JSON.stringify({ subject: "Stainless coil", sentences: [
  { text: "In my 12 years in the steel trade I have rarely seen such a mill.", rests_on: "note:1" },
  { text: "Do you supply to Kenya?", rests_on: "question" }] });
const PASS = `{"verdict":"pass","issues":[]}`, BACK = `{"verdict":"send_back","issues":["sentence 2 says more than fact 1"]}`, BLOCK = `{"verdict":"block","issues":["names a private individual"]}`;
const CASE: OutreachCase = { id: "case-1", kind: "outreach", counterparty: "Harbin Coil Works", material: "products page text ...", brief: "RFQ for stainless coil; destination Mombasa; quantity not yet known" };
const SECRET = "RESEARCHER-PRIVATE-REASONING-7731";

(async () => {
  // ---- flag off -------------------------------------------------------------------------------------------
  delete process.env.AGENT_PIPELINE;
  let w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [PASS] });
  let r = await runCase(w.deps, CASE);
  ok(pipelineOn() === false && r.status === "off" && r.reason === "pipeline is off", "with the flag off runCase refuses: pipeline is off");
  ok(w.calls.length === 0 && w.handoffs.rows.length === 0 && w.budget.rows.length === 0 && !r.proposal, "with the flag off nothing runs: no model call, no hand-off, no reservation");
  process.env.AGENT_PIPELINE = "true";
  ok((await runCase(w.deps, CASE)).status === "off" && w.calls.length === 0, "only AGENT_PIPELINE=1 switches it on");
  process.env.AGENT_PIPELINE = "1";

  // ---- happy path -----------------------------------------------------------------------------------------
  // the researcher adds reasoning around and inside its answer; none of it may reach the next role
  const chatty = `Let me think. ${SECRET}\n${NOTE.replace(/}$/, `,"reasoning":"${SECRET}","verdict":"pass"}`)}\nThat is my note.`;
  w = world({ bd_research: [chatty], bd_opener: [DRAFT], evidence: [PASS] });
  r = await runCase(w.deps, CASE);
  const rows = w.handoffs.rows;
  ok(r.status === "waiting_approval" && !!r.proposal && r.proposal.status === "waiting_approval", "happy path ends in waiting_approval with a proposed message");
  ok(rows.length === 3 && rows.map((x) => x.stage).join(">") === "bd_research>bd_opener>evidence", "three hand-off rows: research, opener, evidence");
  ok(new Set(rows.map((x) => x.run_id)).size === 3 && rows.every((x) => x.run_id && x.case_id === "case-1"), "three distinct run ids, all on the case");
  ok(rows.map((x) => x.persona).join("|") === "Tomas Varga|Isabel Navarro|Omar Haddad" && rows.map((x) => x.role).join("|") === "bd_research|bd_opener|evidence", "each row names its role and persona");
  ok(rows[1].run_id !== rows[2].run_id && r.proposal!.writer.run_id === rows[1].run_id && r.proposal!.checker.run_id === rows[2].run_id && r.proposal!.checker.role === "evidence", "the record shows the checker is a different run from the writer");
  ok(rows[0].verdict === "" && rows[1].verdict === "" && rows[2].verdict === "pass", "only the evidence row carries a verdict");
  ok(rows.every((x) => x.status === "ok" && x.model === "scripted" && x.input_hash.length === 32 && x.started && x.finished && x.reserved_usd > 0 && x.actual_usd !== null && x.actual_usd > 0 && x.actual_usd <= x.reserved_usd), "each row holds input hash, times, model, reserved and actual cost");
  ok(r.model_calls === 3 && w.calls.length === 3 && w.calls.map((c) => c.role).join(",") === "bd_research,bd_opener,evidence", "one model call per stage");
  ok(w.budget.rows.filter((x) => x.kind === "reserve").length === 3 && w.budget.rows.filter((x) => x.kind === "settle" && x.usd !== null).length === 3, "every call was reserved before and settled after");
  ok(r.proposal!.text.includes("304 and 316L") && r.proposal!.sentences.length === 3 && r.proposal!.contact === "sales@example.com" && r.proposal!.evidence.verdict === "pass" && r.proposal!.evidence.issues.length === 0, "the proposal carries the text, the basis of each sentence, the contact and the evidence verdict");

  // ---- isolation between roles ----------------------------------------------------------------------------
  const [cr, co, ce] = w.calls;
  ok(!co.input.includes(systemFor("bd_research")) && !co.system.includes("Tomas Varga") && !co.input.includes("Tomas Varga"), "the opener's input does not contain the researcher's instructions or persona");
  ok(!co.input.includes(SECRET) && !ce.input.includes(SECRET) && !rows[0].output.includes(SECRET), "the researcher's reasoning is dropped: it reaches neither the opener, the checker nor the record");
  ok(co.input.includes("316L") && co.input.includes("account_note") && !co.input.includes('"verdict"'), "the opener sees the account note, without any verdict field the researcher tried to add");
  ok(ce.system.includes("Omar Haddad") && ce.system !== co.system && !ce.system.includes("Isabel Navarro") && ce.input.includes("account_note") && ce.input.includes("Do you supply this range to Kenya?"), "the checker has its own instructions and receives the account note and the draft");
  ok(!ce.input.includes(co.system.slice(0, 80)) && !cr.input.includes("316L"), "the checker does not see the writer's instructions; the researcher sees only the case material");
  ok(w.calls.every((c) => c.maxOutputTokens > 0 && c.maxOutputTokens <= 1200 && Buffer.byteLength(c.input) <= MAX_INPUT_BYTES), "every call has a bounded output and a bounded input");

  // ---- the rule check overrides a checker that says pass --------------------------------------------------
  w = world({ bd_research: [NOTE], bd_opener: [BIO_DRAFT, DRAFT], evidence: [PASS] });
  r = await runCase(w.deps, { ...CASE, id: "case-2" });
  const ev = w.handoffs.rows.filter((x) => x.stage === "evidence");
  ok(ev.length === 2 && ev[0].verdict === "send_back" && ev[0].output.includes("rule:invented_personal_history"), "'in my 12 years in the steel trade' is sent back by the rule check although the checker said pass");
  ok(w.calls[3].role === "bd_opener" && w.calls[3].input.includes("sent_back_for") && w.calls[3].input.includes("invented_personal_history"), "the writer is asked again and told why");
  ok(r.status === "waiting_approval" && !r.proposal!.text.includes("12 years") && r.proposal!.writer.run_id === w.handoffs.rows[3].run_id, "the rewritten draft passes; the proposal is the second draft, not the first");
  w = world({ bd_research: [NOTE], bd_opener: [BIO_DRAFT], evidence: [PASS] });
  r = await runCase(w.deps, { ...CASE, id: "case-2b" });
  ok(r.status === "needs_owner" && !r.proposal, "a writer that keeps the invented past never reaches the owner as a proposal, whatever the checker says");
  w = world({ bd_research: [NOTE], bd_opener: [JSON.stringify({ subject: "x", sentences: [{ text: "Your mill is the largest in Asia.", rests_on: "" }] }), DRAFT], evidence: [PASS] });
  r = await runCase(w.deps, { ...CASE, id: "case-2c" });
  ok(w.handoffs.rows.filter((x) => x.stage === "evidence")[0].output.includes("rule:sentence_without_basis"), "a sentence with nothing it rests on is sent back");

  // ---- rewrite limit --------------------------------------------------------------------------------------
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [BACK] });
  r = await runCase(w.deps, { ...CASE, id: "case-3" });
  const roles = w.calls.map((c) => c.role).join(",");
  ok(r.status === "needs_owner" && !r.proposal, "a draft that keeps being sent back stops as needs_owner");
  ok(roles === "bd_research,bd_opener,evidence,bd_opener,evidence,bd_opener,evidence", "the draft is rewritten after the first and second send-back (two retries), and the third send-back ends the case");
  ok(w.handoffs.rows.filter((x) => x.verdict === "send_back").length === 3 && new Set(w.handoffs.rows.map((x) => x.run_id)).size === 7, "every attempt is its own run with its own row");
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [BACK, BACK, PASS] });
  r = await runCase(w.deps, { ...CASE, id: "case-3b" });
  ok(r.status === "waiting_approval" && r.model_calls === 7, "two send-backs and then a pass still reaches waiting_approval");
  w = world({ bd_research: ["I could not find anything."], bd_opener: [DRAFT], evidence: [PASS] });
  r = await runCase(w.deps, { ...CASE, id: "case-3c" });
  ok(r.status === "needs_owner" && w.calls.length === 3 && w.calls.every((c) => c.role === "bd_research") && w.handoffs.rows.every((x) => x.status === "unreadable_output"), "a researcher with no usable note is asked three times, then the owner decides; no writer runs");
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: ["looks fine to me"] });
  r = await runCase(w.deps, { ...CASE, id: "case-3d" });
  ok(r.status === "needs_owner" && w.handoffs.rows.filter((x) => x.stage === "evidence").every((x) => x.verdict === "send_back"), "a checker answer that cannot be read is a send-back, never a pass");

  // ---- block ----------------------------------------------------------------------------------------------
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [BLOCK] });
  r = await runCase(w.deps, { ...CASE, id: "case-4" });
  ok(r.status === "blocked" && !r.proposal && r.verdict?.verdict === "block" && w.calls.length === 3, "a block verdict stops the case at once: no proposal, no rewrite");
  const wRow = w.handoffs.rows[1], cRow = w.handoffs.rows[2], d = asDraft(parseArtefact(DRAFT))!;
  ok(typeof proposalFor("case-4", d, "", wRow, cRow, { verdict: "block", issues: [] }) === "string" && typeof proposalFor("case-4", d, "", wRow, cRow, { verdict: "pass", issues: [] }) === "string", "the gate refuses a block verdict, and refuses a pass when the recorded check says block");
  const passRow: Handoff = { ...cRow, verdict: "pass" };
  ok(typeof proposalFor("case-4", d, "", wRow, passRow, { verdict: "pass", issues: [] }) === "object", "the gate opens only for a recorded pass by the evidence role on another run");
  ok(typeof proposalFor("case-4", d, "", wRow, passRow, { verdict: "pass", issues: ["one open point"] }) === "string", "the gate refuses a pass with unresolved issues");
  ok(typeof proposalFor("case-4", d, "", wRow, { ...passRow, run_id: wRow.run_id }, { verdict: "pass", issues: [] }) === "string", "the gate refuses when the checker's run is the writer's run");
  ok(typeof proposalFor("case-4", d, "", wRow, { ...passRow, role: "bd_opener" }, { verdict: "pass", issues: [] }) === "string" && typeof proposalFor("case-4", d, "", { ...wRow, role: "evidence" }, passRow, { verdict: "pass", issues: [] }) === "string", "the gate refuses a check by a non-evidence role and a draft written by the evidence role");
  ok(typeof proposalFor("other", d, "", wRow, passRow, { verdict: "pass", issues: [] }) === "string", "the gate refuses hand-offs of another case");
  const cv = (m: Verdict, rule: string[]) => combineVerdict(m, rule).verdict;
  ok(cv({ verdict: "pass", issues: [] }, []) === "pass" && cv({ verdict: "pass", issues: ["x"] }, []) === "send_back" && cv({ verdict: "pass", issues: [] }, ["false_urgency"]) === "send_back" && cv({ verdict: "block", issues: [] }, ["x"]) === "block" && cv({ verdict: "send_back", issues: [] }, []) === "send_back", "pass needs zero issues from both the checker and the rules; a block stays a block");
  let threw = false;
  try { await new MemoryHandoffStore().append({ ...wRow, verdict: "pass" }); } catch { threw = true; }
  ok(threw, "the hand-off store refuses a verdict on a writer's row: a role cannot record its own verdict");

  // ---- budget ---------------------------------------------------------------------------------------------
  // room for exactly two calls: the third reservation is refused mid-case
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [PASS] });
  const probe = await runCase(w.deps, { ...CASE, id: "probe" });
  const perCall = Math.max(...probe.handoffs.map((x) => x.reserved_usd));
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [PASS] }, { budgetConfig: { ...cfg, dayUsd: perCall * 2.5 } });
  // a model that reports no usage: the two calls stay counted at their worst case, so the third cannot fit
  const silent: ModelCall = async (a) => { w.calls.push(a); return { text: a.role === "bd_research" ? NOTE : a.role === "bd_opener" ? DRAFT : PASS }; };
  r = await runCase({ ...w.deps, model: silent }, { ...CASE, id: "case-5" });
  ok(r.status === "budget_stopped" && r.reason === "day_cap" && !r.proposal, "a budget refusal mid-case stops it as budget_stopped with the reason");
  ok(w.calls.length === 2 && r.model_calls === 2 && w.calls.map((c) => c.role).join(",") === "bd_research,bd_opener", "no model call is made after the refusal");
  const lastRow = w.handoffs.rows[w.handoffs.rows.length - 1];
  ok(lastRow.status === "budget_refused" && lastRow.note === "day_cap" && lastRow.stage === "evidence" && w.handoffs.rows.length === 3, "the refusal is on record against the stage that could not run");
  ok(w.budget.rows.filter((x) => x.kind === "settle").every((x) => x.usd === null), "calls without usage are settled as unknown and stay at the worst case");
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [PASS] }, { now: () => Date.parse("2026-11-20T10:00:00Z") });
  r = await runCase(w.deps, { ...CASE, id: "case-5b" });
  ok(r.status === "budget_stopped" && r.reason === "outside_period" && w.calls.length === 0, "outside the budget period no call is made at all");
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [PASS] }, { pricesKnown: () => false });
  r = await runCase(w.deps, { ...CASE, id: "case-5c" });
  ok(r.status === "budget_stopped" && r.reason === "unbounded" && w.calls.length === 0, "a model whose prices are not known cannot be bounded: no call");
  w = world({ bd_research: [NOTE], bd_opener: [new Error("Anthropic 529: overloaded")], evidence: [PASS] });
  r = await runCase(w.deps, { ...CASE, id: "case-5d" });
  ok(r.status === "failed" && w.calls.length === 2 && w.budget.rows.filter((x) => x.kind === "settle").pop()!.usd === null && w.handoffs.rows[1].status === "model_error" && w.handoffs.rows[1].actual_usd === null, "a failed call stops the case, is recorded, and its reservation stays at the worst case; nothing is retried or queued");
  w = world({ bd_research: [NOTE], bd_opener: [DRAFT], evidence: [PASS] });
  r = await runCase(w.deps, { ...CASE, id: "case-5e", material: "x ".repeat(4000) + '"'.repeat(8000) });
  ok(r.status !== "waiting_approval" || w.calls.every((c) => Buffer.byteLength(c.input) <= MAX_INPUT_BYTES), "oversized material never produces a call over the input bound");
  ok(clip("שלום עולם", 7) === "שלו" && Buffer.byteLength(clip("a".repeat(50), 10)) === 10, "clipping counts bytes and does not split a character");

  // ---- reply case: memory -> follow-up -> evidence --------------------------------------------------------
  const CARD = JSON.stringify({ timeline: [{ date: "2026-11-05", who: "us", text: "asked whether they supply 316L coil to Kenya" }, { date: "2026-11-09", who: "them", text: "yes, MOQ 20 tonnes, asked for destination port" }],
    open_promises: [{ by: "us", text: "name the destination port" }], preferences: ["prefers e-mail"], last_message: "yes, MOQ 20 tonnes, which port?", last_date: "2026-11-09" });
  const SEND = JSON.stringify({ decision: "send", reason: "they asked a question we can answer", wait_until: "", draft: { subject: "Re: coil", sentences: [{ text: "Thank you for your reply.", rests_on: "courtesy" }, { text: "The destination port is Mombasa.", rests_on: "brief:destination Mombasa" }] } });
  const REPLY: ReplyCase = { id: "case-6", kind: "reply", counterparty: "Harbin Coil Works", brief: "destination Mombasa", contact: "sales@example.com",
    thread: [{ date: "2026-11-05", from: "us", text: "Do you supply 316L coil to Kenya?" }, { date: "2026-11-09", from: "them", text: "Yes, MOQ 20 tonnes. Which port?" }] };
  w = world({ bd_memory: [CARD], bd_followup: [SEND], evidence: [PASS] });
  r = await runCase(w.deps, REPLY);
  ok(r.status === "waiting_approval" && w.handoffs.rows.map((x) => `${x.stage}:${x.persona}`).join(">") === "bd_memory:Ingrid Solberg>bd_followup:Kwame Asante>evidence:Omar Haddad" && r.proposal!.text.includes("Mombasa"), "a reply case runs memory, follow-up and the evidence check as three runs");
  ok(w.calls[1].input.includes("relationship_card") && !w.calls[1].input.includes("Which port?") && w.calls[2].input.includes("relationship_card"), "the follow-up writer and the checker see the relationship card, not the raw thread");
  w = world({ bd_memory: [CARD], bd_followup: [JSON.stringify({ decision: "wait", reason: "holiday week in the counterparty's region", wait_until: "2026-11-16", draft: null })], evidence: [PASS] });
  r = await runCase(w.deps, { ...REPLY, id: "case-6b" });
  ok(r.status === "no_message" && r.decision?.decision === "wait" && r.decision.wait_until === "2026-11-16" && !r.proposal && w.calls.length === 2, "a decision to wait ends the case without a message and without a check");
  r = await runCase(world({ bd_memory: [CARD] }).deps, { ...REPLY, id: "case-6c", thread: [{ date: "2026-11-05", from: "us", text: "hello" }] });
  ok(r.status === "failed" && r.model_calls === 0, "the later stages need a reply to exist");

  // ---- record format --------------------------------------------------------------------------------------
  const back = cellsToHandoff(handoffToCells(passRow));
  ok(!!back && back.run_id === passRow.run_id && back.verdict === "pass" && back.role === "evidence" && Math.abs(back.reserved_usd - passRow.reserved_usd) < 1e-6 && back.input_hash === passRow.input_hash, "a hand-off row survives the sheet");
  process.env.STATE_SHEET_ID = "state-sheet-for-test";
  ok(sheetFor("Agent Handoffs") === "state-sheet-for-test", "the hand-off tab is registered as a state tab");
  delete process.env.STATE_SHEET_ID;

  process.exit(fail ? 1 : 0);
})();
