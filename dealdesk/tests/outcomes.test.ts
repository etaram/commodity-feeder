// Outcome ledger checks (F11 "Historical learning"). Every case below is a synthetic test fixture, not a Sinder deal.
import { assertNoLeakage, caseStatus, createLedger, eventProblems, EVENT_TYPES, memoryStore, REASONS, snapshot, type Feature, type OutcomeEvent } from "@/lib/outcomes";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const throws = (f: () => unknown) => { try { f(); return false; } catch { return true; } };
const rejects = async (f: () => Promise<unknown>) => { try { await f(); return false; } catch { return true; } };
const ev = (type: OutcomeEvent["type"], at: string, over: Partial<OutcomeEvent> = {}): OutcomeEvent => ({
  type, case_id: "C1", route_id: "R1", workspace: "sinder", at, actor: "analyst@test", counterparty: "Test Buyer", proof: { kind: "message", id: `msg-${type}-${at}` },
  rights_scope: "own", model_version: "rules-test", display_rank: null, reason: null, ...over });

(async () => {
  ok(EVENT_TYPES.join(",") === "signal_found,need_confirmed,technical_match,rfq_authorized,rfq_sent,rfq_responded,quote_received,proposal_delivered,negotiation_advanced,contract_signed,delivered_invoiced,cash_collected,lost,abandoned", "event types are in funnel order");
  ok(REASONS.length === 12 && REASONS.includes("uncompetitive_price") && REASONS.includes("other"), "the reason list is fixed");

  // --- validation
  const L = createLedger(memoryStore());
  ok((await L.record(ev("signal_found", "2026-11-12T09:00:00Z", { proof: { kind: "source", id: "src-1" }, counterparty: "" }))).stored, "an event with proof is stored");
  ok(await rejects(() => L.record({ ...ev("rfq_sent", "2026-11-13T09:00:00Z"), proof: undefined as never })), "an event without proof is rejected");
  ok(await rejects(() => L.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { proof: { kind: "message", id: "  " } }))), "an empty proof id is rejected");
  ok(await rejects(() => L.record(ev("lost", "2026-11-20T09:00:00Z"))), "lost without a reason is rejected");
  ok(await rejects(() => L.record(ev("lost", "2026-11-20T09:00:00Z", { reason: "they went quiet" as never }))), "a reason outside the fixed list is rejected");
  ok(await rejects(() => L.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { reason: "timing" }))), "a reason on a positive event is rejected");
  ok(await rejects(() => L.record(ev("rfq_sent", "yesterday"))), "an unreadable time is rejected");
  ok(await rejects(() => L.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { rights_scope: "shared" as never }))), "an unknown rights scope is rejected");
  ok(await rejects(() => L.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { display_rank: 0 }))), "display_rank 0 is rejected (null or 1 and up)");
  ok(await rejects(() => L.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { workspace: "../etc" }))), "an invalid workspace is rejected, not defaulted");
  ok(await rejects(() => L.record(ev("won" as never, "2026-11-13T09:00:00Z"))), "an unknown event type is rejected");
  ok((await L.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { display_rank: 3 }))).stored && !(await L.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { display_rank: 3 }))).stored, "an exact repeat is not stored twice");
  ok((await L.caseEvents("sinder", "C1")).length === 2, "rejected events left nothing behind");

  // --- status labels
  const st = (e: OutcomeEvent[], now: string, d = 14) => caseStatus(e, now, d);
  const none = st([], "2026-11-13T00:00:00Z");
  ok(none.label === "not_contacted" && none.stage === null && !none.known_negative && none.censored, "a case with no events is not_contacted: unknown, not negative");
  const unsent = st([ev("signal_found", "2026-11-01T00:00:00Z"), ev("technical_match", "2026-11-02T00:00:00Z"), ev("rfq_authorized", "2026-11-03T00:00:00Z")], "2027-06-01T00:00:00Z");
  ok(unsent.label === "not_contacted" && unsent.stage === "rfq_authorized" && !unsent.known_negative, "an unsent prospect is not_contacted, not lost, however long ago");
  const sent = [ev("signal_found", "2026-11-01T00:00:00Z"), ev("rfq_sent", "2026-11-03T00:00:00Z")];
  ok(st(sent, "2026-11-10T00:00:00Z").label === "pending", "rfq sent, inside the follow-up window: pending");
  ok(st(sent, "2026-11-17T00:00:00Z").label === "pending" && st(sent, "2026-11-17T00:00:01Z").label === "no_response_censored", "the window edge: day 14 still pending, after it no_response_censored");
  const cens = st(sent, "2026-12-20T00:00:00Z");
  ok(cens.label === "no_response_censored" && !cens.known_negative && cens.censored && cens.stage === "rfq_sent", "no reply after the window is censored, never lost");
  ok(st([...sent, ev("rfq_sent", "2026-12-15T00:00:00Z")], "2026-12-20T00:00:00Z").label === "pending", "a follow-up message restarts the window");
  const replied = [...sent, ev("rfq_responded", "2026-12-01T00:00:00Z"), ev("quote_received", "2026-12-05T00:00:00Z")];
  ok(st(replied, "2027-03-01T00:00:00Z").label === "quote_received" && !st(replied, "2027-03-01T00:00:00Z").censored, "positive stages are reported as reached");
  ok(st(replied, "2026-12-02T00:00:00Z").label === "rfq_responded" && st(replied, "2026-11-10T00:00:00Z").label === "pending", "status is read as of `now`: later events are not visible earlier");
  const lost = st([...replied, ev("lost", "2026-12-10T00:00:00Z", { reason: "uncompetitive_price" })], "2027-01-01T00:00:00Z");
  ok(lost.label === "lost" && lost.known_negative && lost.reason === "uncompetitive_price" && lost.stage === "quote_received", "lost only with a recorded lost event; the furthest stage is kept");
  const ab = st([...sent, ev("abandoned", "2026-11-05T00:00:00Z", { reason: "poor_signal" })], "2027-01-01T00:00:00Z");
  ok(ab.label === "abandoned" && !ab.known_negative, "abandoned is our own decision, not a known negative");
  ok(st([...sent, ev("abandoned", "2026-11-05T00:00:00Z", { reason: "timing" }), ev("rfq_responded", "2026-11-20T00:00:00Z")], "2027-01-01T00:00:00Z").label === "rfq_responded", "a later verified reply reopens an abandoned case");
  const noProof = st([ev("signal_found", "2026-11-01T00:00:00Z"), { ...ev("contract_signed", "2026-11-02T00:00:00Z"), proof: { kind: "document", id: "" } }], "2027-01-01T00:00:00Z");
  ok(noProof.label === "not_contacted" && noProof.stage === "signal_found" && noProof.ignored.length === 1, "an unproven event does not advance the case");
  ok(throws(() => st([ev("rfq_sent", "2026-11-03T00:00:00Z"), ev("rfq_sent", "2026-11-03T00:00:00Z", { case_id: "C2" })], "2026-11-10T00:00:00Z")), "events of two cases are not read as one");
  ok(throws(() => st(sent, "now")) && throws(() => st(sent, "2026-11-10T00:00:00Z", 0)), "an unreadable clock or window is refused");

  // --- a public winner is not an internal closed deal
  const award = ev("contract_signed", "2023-06-15T00:00:00Z", { rights_scope: "public", proof: { kind: "source", id: "public-award-notice-1" }, counterparty: "Fixture Winner Ltd" });
  ok(/public/.test(eventProblems(award).join(" ")) && await rejects(() => L.record(award)), "a public award cannot be recorded as contract_signed");
  const pub = st([ev("signal_found", "2023-06-15T00:00:00Z", { rights_scope: "public", proof: { kind: "source", id: "public-award-notice-1" } }), award], "2026-11-13T00:00:00Z");
  ok(pub.label === "not_contacted" && pub.stage === "signal_found" && pub.ignored.length === 1, "a public winner is not an internal closed deal: the case stays not_contacted");

  // --- point in time and leakage (specification fixture: backtest a 2023 award)
  const hist = [ev("signal_found", "2023-01-10T00:00:00Z"), ev("rfq_sent", "2023-02-01T00:00:00Z"), ev("rfq_responded", "2025-03-04T00:00:00Z")];
  ok(snapshot(hist, "2023-06-14T23:59:59Z").length === 2 && snapshot(hist, "2023-01-10T00:00:00Z").length === 1 && snapshot(hist, "2022-12-31T00:00:00Z").length === 0, "snapshot returns only events at or before asOf");
  ok(caseStatus(snapshot(hist, "2023-06-14T23:59:59Z"), "2023-06-14T23:59:59Z", 14).label === "no_response_censored", "the 2023 view does not know about the 2025 reply");
  const asOf = "2023-06-14T23:59:59Z";   // the day before the 2023 award was published
  const before: Feature[] = [
    { name: "supplier_awards_2021", observed_at: "2021-09-01", value: 2 },
    { name: "supplier_awards_2022", observed_at: "2022-11-20", value: 1 },
    { name: "buyer_awards_before", observed_at: "2023-05-30", value: 7 }];
  ok(!throws(() => assertNoLeakage(before, asOf)), "backtest of the 2023 award with observations dated before it passes");
  ok(throws(() => assertNoLeakage([...before, { name: "supplier_win_2024", observed_at: "2024-04-02", value: 1 }], asOf)), "the supplier's 2024 win in the features fails the check");
  ok(throws(() => assertNoLeakage([...before, { name: "email_reply_2025", observed_at: "2025-03-04T10:00:00Z", value: true }], asOf)), "a 2025 e-mail reply in the features fails the check");
  ok(throws(() => assertNoLeakage([...before, { name: "the_award_itself", observed_at: "2023-06-15", value: 1 }], asOf)), "the award being backtested cannot be its own feature");
  ok(throws(() => assertNoLeakage([{ name: "undated", observed_at: "" }], asOf)), "a feature with no observation time fails: nothing proves it is earlier");
  let msg = ""; try { assertNoLeakage([...before, { name: "supplier_win_2024", observed_at: "2024-04-02" }], asOf); } catch (e) { msg = String(e); }
  ok(/supplier_win_2024/.test(msg) && !/supplier_awards_2021/.test(msg), "the error names the leaking feature only");

  // --- rights and workspaces
  const M = createLedger(memoryStore());
  await M.record(ev("rfq_sent", "2026-11-13T09:00:00Z", { case_id: "A1", workspace: "acme", rights_scope: "client_confidential" }));
  await M.record(ev("rfq_sent", "2026-11-13T10:00:00Z", { case_id: "A2", workspace: "acme" }));
  await M.record(ev("signal_found", "2026-11-13T11:00:00Z", { case_id: "A3", workspace: "acme", rights_scope: "public", proof: { kind: "source", id: "s-9" } }));
  await M.record(ev("rfq_sent", "2026-11-13T12:00:00Z", { case_id: "S1", rights_scope: "client_confidential" }));
  await M.record(ev("rfq_sent", "2026-11-13T13:00:00Z", { case_id: "S2" }));
  const ids = (x: OutcomeEvent[]) => x.map((e) => e.case_id).sort().join(",");
  ok(ids(await M.list("acme")) === "A1,A2,A3", "a workspace lists all of its own events");
  ok(ids(await M.list("sinder")) === "A3,S1,S2", "another workspace sees neither client-confidential nor own events of acme, only public ones");
  ok(!(await M.caseEvents("sinder", "A1")).length && (await M.caseEvents("acme", "A1")).length === 1, "a case id guessed from another workspace returns nothing");
  const exA = await M.exportForLearning("acme"), exS = await M.exportForLearning("sinder");
  ok(ids(exA) === "A2,A3" && ids(exS) === "A3,S2", "exportForLearning holds own and public rows only");
  ok(![...exA, ...exS, ...(await M.pooledExport())].some((e) => e.rights_scope === "client_confidential"), "client-confidential events appear in no export");
  ok(ids(await M.pooledExport()) === "A3", "the pooled export is public rows only");
  ok(await rejects(() => M.list("")) && await rejects(() => M.exportForLearning("Acme Corp")), "listing and export need a valid workspace");
  const got = (await M.list("acme"))[0]; got.proof.id = "tampered";
  ok((await M.list("acme"))[0].proof.id !== "tampered", "a reader cannot alter stored events");

  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})();
