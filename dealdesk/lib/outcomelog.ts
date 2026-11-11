// Ledger events from real actions that already exist in the product (an approved message that was sent, a saved
// quote, a feedback reason). One rule: a failure to write the ledger never blocks the action it describes. logOutcome
// catches everything, waits at most a few seconds, logs the failure and returns false.
import { asWs } from "@/lib/auth";
import { logEvent } from "@/lib/log";
import { createLedger, FEEDBACK, type OutcomeEvent, type OutcomeStore, type Reason } from "@/lib/outcomes";
import { sheetsOutcomeStore } from "@/lib/outcomestore-sheets";

const WAIT_MS = 6000;
const cut = (v: unknown, n: number) => String(v ?? "").replace(/[\r\n\t]+/g, " ").trim().slice(0, n);

/** Record one event. Never throws and never waits longer than WAIT_MS. True only when the row was stored now. */
export async function logOutcome(e: OutcomeEvent, store: OutcomeStore = sheetsOutcomeStore()): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const r = await Promise.race([createLedger(store).record(e), new Promise<never>((_, no) => { timer = setTimeout(() => no(new Error("the ledger did not answer in time")), WAIT_MS); })]);
    return r.stored;
  } catch (x) {
    await logEvent("warn", "outcomes", `ledger write failed for ${e?.type}`, `${e?.case_id}: ${String((x as Error)?.message || x)}`).catch(() => {});
    return false;
  } finally { if (timer) clearTimeout(timer); }
}

// A deal carries one route in this release, so the deal id is both the case id and the route id of its events.
type Base = { workspace: string; deal_id: string; at: string; actor: string; counterparty?: string; model_version?: string };
const base = (b: Base) => ({ case_id: cut(b.deal_id, 120), route_id: cut(b.deal_id, 120), workspace: asWs(b.workspace), at: b.at, actor: cut(b.actor, 160) || "unknown",
  counterparty: cut(b.counterparty, 200), rights_scope: "own" as const, model_version: cut(b.model_version, 80) || "none", display_rank: null, reason: null });

/** The owner approved one message and the send guard reports it sent: rfq_authorized (proof: the approval) and rfq_sent (proof: the message id). */
export async function logRfqSent(b: Base & { approval_ref: string; message_id: string }, store?: OutcomeStore): Promise<void> {
  if (!b.deal_id || !b.approval_ref) return;
  await logOutcome({ ...base(b), type: "rfq_authorized", proof: { kind: "message", id: cut(b.approval_ref, 200) } }, store);
  await logOutcome({ ...base(b), type: "rfq_sent", proof: { kind: "message", id: cut(b.message_id, 200) || cut(b.approval_ref, 200) } }, store);
}

/** A quote record was saved on a deal for the first time: quote_received (proof: the record and the source the saver stated). */
export async function logQuoteReceived(b: Base & { record_id: string; source_ref: string }, store?: OutcomeStore): Promise<void> {
  if (!b.deal_id || !b.record_id || !cut(b.source_ref, 10)) return; // no stated source, no proof, no event
  await logOutcome({ ...base(b), type: "quote_received", proof: { kind: "document", id: cut(`deal ${b.deal_id} quote ${b.record_id}: ${b.source_ref}`, 300) } }, store);
}

/** An owner's or analyst's feedback reason on a deal. A label, not an outcome (see FEEDBACK in lib/outcomes.ts). */
export async function logFeedback(b: Base & { reason: Reason }, store?: OutcomeStore): Promise<boolean> {
  return logOutcome({ ...base(b), type: FEEDBACK, reason: b.reason, proof: { kind: "source", id: cut(`deal ${b.deal_id}`, 200) } }, store);
}
