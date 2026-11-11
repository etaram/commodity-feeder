// Outcome ledger on Sheets (lib/outcomestore-sheets.ts) against an in-memory grid, and the event helpers of
// lib/outcomelog.ts (sent RFQ, received quote, feedback). No Google, no network, nothing is sent.
import { readFileSync } from "node:fs";
import { caseStatus, createLedger, eventProblems, EVENT_TYPES, FEEDBACK, REASONS, type OutcomeEvent, type OutcomeStore } from "@/lib/outcomes";
import { logFeedback, logOutcome, logQuoteReceived, logRfqSent } from "@/lib/outcomelog";
import { cellsToOutcome, outcomeToCells, OUTCOMES_TAB, SheetsOutcomeStore } from "@/lib/outcomestore-sheets";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
function world() {
  const grid: string[][] = [];
  const store = new SheetsOutcomeStore({ read: async () => grid.map((r) => [...r]), append: async (cells) => { grid.push(cells.map(String)); } });
  return { grid, store, L: createLedger(store) };
}
const ev = (o: Partial<OutcomeEvent> = {}): OutcomeEvent => ({ type: "rfq_sent", case_id: "T-1", route_id: "T-1", workspace: "sinder", at: "2026-11-11T09:00:00Z", actor: "owner@example.org", counterparty: "Fixture Pumps Ltd",
  proof: { kind: "message", id: "<id-1@example.org>" }, rights_scope: "own", model_version: "none", display_rank: null, reason: null, ...o });

(async () => {
  ok(OUTCOMES_TAB === "Outcomes", "the tab is called Outcomes");
  const sheets = readFileSync("lib/sheets.ts", "utf8"), tabs = sheets.slice(sheets.indexOf("const STATE_TABS"), sheets.indexOf("const tabOf"));
  ok(tabs.includes('"Outcomes"') && tabs.includes('"Missions"'), "Outcomes is registered in STATE_TABS, next to Missions");

  // ---- round trip, one row per event, an exact repeat is not stored twice
  const { grid, store, L } = world();
  const a = await L.record(ev()), b = await L.record(ev());
  ok(a.stored && !b.stored && grid.length === 1, "record through the sheet: one row; the same event again adds none");
  ok(grid[0].length === 7 && grid[0][0] === "2026-11-11T09:00:00Z" && grid[0][1] === "sinder" && grid[0][2] === "T-1" && grid[0][4] === "rfq_sent" && grid[0][5] === "message:<id-1@example.org>", "row: time, workspace, case, route, type, proof, JSON (7 columns)");
  ok(JSON.stringify((await store.all())[0]) === JSON.stringify(ev()) && JSON.stringify(cellsToOutcome(outcomeToCells(ev()).map(String))) === JSON.stringify(ev()), "an event survives the round trip unchanged");
  await L.record(ev({ type: "rfq_authorized", proof: { kind: "message", id: "Agent Approvals:M1" } }));
  await L.record(ev({ workspace: "acme", case_id: "A-1", route_id: "A-1" }));
  ok((await L.list("sinder")).length === 2 && (await L.list("acme")).length === 1 && (await L.caseEvents("acme", "T-1")).length === 0 && (await L.caseEvents("sinder", "T-1")).length === 2, "the ledger over the sheet keeps workspaces apart");
  ok(caseStatus(await L.caseEvents("sinder", "T-1"), "2026-11-12T00:00:00Z", 14).label === "pending", "the case reads as sent and pending from the stored rows");

  // ---- nothing unproven or broken gets in or comes out
  let threw = false;
  try { await L.record(ev({ proof: { kind: "message", id: "" } })); } catch { threw = true; }
  let threw2 = false;
  try { await store.append(ev({ workspace: "" })); } catch { threw2 = true; }
  ok(threw && threw2 && grid.length === 3, "an event without proof or without a workspace is refused and writes no row");
  grid.push(["2026-11-11", "sinder", "T-1", "T-1", "rfq_sent", "message:x", "not json"], ["2026-11-11", "", "T-1", "T-1", "rfq_sent", "message:x", JSON.stringify(ev())],
    ["2026-11-11", "acme", "T-1", "T-1", "contract_signed", "document:x", JSON.stringify(ev({ type: "contract_signed" }))], ["2026-11-11", "sinder", "T-1", "T-1", "contract_signed", "", JSON.stringify(ev({ type: "contract_signed", proof: { kind: "document", id: "" } }))]);
  ok((await store.all()).length === 3 && (await L.caseEvents("acme", "T-1")).length === 0, "rows with broken JSON, no workspace, a workspace cell that disagrees with the event, or no proof are ignored");
  threw = false;
  try { outcomeToCells(ev({ counterparty: "x".repeat(9000) })); } catch { threw = true; }
  ok(threw, "an oversized event is refused, not cut");
  const empty = new SheetsOutcomeStore({ read: async () => [], append: async () => {} });
  ok((await empty.all()).length === 0, "a tab that does not exist yet reads as no events");

  // ---- feedback: a label with a reason from the fixed list, never an outcome
  ok(!(EVENT_TYPES as readonly string[]).includes(FEEDBACK) && eventProblems(ev({ type: FEEDBACK, reason: "wrong_spec", proof: { kind: "source", id: "deal T-1" } })).length === 0, "feedback is accepted with a reason and is not a funnel or terminal event");
  ok(eventProblems(ev({ type: FEEDBACK, reason: null })).some((p) => /needs a reason/.test(p)) && eventProblems(ev({ type: FEEDBACK, reason: "because" as never })).length === 1
    && eventProblems(ev({ type: FEEDBACK, reason: "timing", rights_scope: "public" })).some((p) => /public/.test(p)) && eventProblems(ev({ reason: "timing" })).length === 1, "feedback needs a reason from the list and cannot be public; other events still take no reason");
  const w = world();
  ok(await logFeedback({ workspace: "sinder", deal_id: "T-1", at: "2026-11-11T10:00:00Z", actor: "analyst@example.org", reason: "uncompetitive_price" }, w.store), "logFeedback stores the event");
  const fb = (await w.store.all())[0];
  ok(fb.type === "feedback" && fb.reason === "uncompetitive_price" && fb.actor === "analyst@example.org" && fb.case_id === "T-1" && fb.rights_scope === "own" && fb.proof.id === "deal T-1" && REASONS.includes(fb.reason!), "the feedback row carries the deal, the person and the reason");
  await w.L.record(ev());
  const st = caseStatus(await w.L.caseEvents("sinder", "T-1"), "2026-11-12T00:00:00Z", 14);
  ok(st.label === "pending" && st.known_negative === false && st.reason === null && st.ignored.length === 0, "feedback never changes a case's stage, never closes it and is never a known negative");
  ok(caseStatus([fb], "2026-11-12T00:00:00Z", 14).label === "not_contacted", "feedback alone is not a contact");

  // ---- events from real actions
  const x = world(), base = { workspace: "sinder", deal_id: "T-2", at: "2026-11-11T11:00:00Z", actor: "owner@example.org", counterparty: "Fixture Pumps Ltd" };
  await logRfqSent({ ...base, approval_ref: "Agent Approvals:M7", message_id: "<m7@example.org>", model_version: "fixture-model" }, x.store);
  await logRfqSent({ ...base, approval_ref: "Agent Approvals:M7", message_id: "<m7@example.org>", model_version: "fixture-model" }, x.store);
  const sent = await x.store.all();
  ok(sent.length === 2 && sent[0].type === "rfq_authorized" && sent[0].proof.id === "Agent Approvals:M7" && sent[1].type === "rfq_sent" && sent[1].proof.id === "<m7@example.org>" && sent.every((e) => e.proof.kind === "message" && e.model_version === "fixture-model"),
    "a sent, approved message: rfq_authorized with the approval id and rfq_sent with the message id, once");
  await logRfqSent({ ...base, approval_ref: "", message_id: "<m@x>" }, x.store);
  await logRfqSent({ ...base, deal_id: "", approval_ref: "Agent Approvals:M8", message_id: "<m@x>" }, x.store);
  ok((await x.store.all()).length === 2, "no approval reference or no deal: no event");
  await logQuoteReceived({ ...base, record_id: "Q1", source_ref: "quotation QF-77 (pdf)" }, x.store);
  await logQuoteReceived({ ...base, record_id: "Q2", source_ref: "" }, x.store);
  const q = (await x.store.all()).filter((e) => e.type === "quote_received");
  ok(q.length === 1 && q[0].proof.kind === "document" && q[0].proof.id === "deal T-2 quote Q1: quotation QF-77 (pdf)" && q[0].model_version === "none" && q[0].counterparty === "Fixture Pumps Ltd", "a saved quote: quote_received with the record and its stated source as proof; no source, no event");
  ok(caseStatus(await x.L.caseEvents("sinder", "T-2"), "2026-11-12T00:00:00Z", 14).label === "quote_received", "the case reads quote_received from those rows");

  // ---- a ledger failure never blocks the action
  const broken: OutcomeStore = { append: async () => { throw new Error("sheet down"); }, all: async () => { throw new Error("sheet down"); } };
  let blew = false, r = true;
  try { r = await logOutcome(ev(), broken); await logRfqSent({ ...base, approval_ref: "Agent Approvals:M9", message_id: "<m9@x>" }, broken); await logQuoteReceived({ ...base, record_id: "Q9", source_ref: "email" }, broken); } catch { blew = true; }
  ok(!blew && r === false && (await logFeedback({ ...base, reason: "timing" }, broken)) === false, "a store that throws: the helpers return false, log and never throw");
  ok((await logOutcome(ev({ proof: { kind: "message", id: "" } }), x.store)) === false && (await x.store.all()).length === 3, "an invalid event is logged and dropped, not thrown");
  if (fail) { console.log(`${fail} failed`); process.exit(1); }
})();
