// Drafts kept on a deal (lib/deal.ts kind "draft") connected to the EXISTING approve-and-send flow. Nothing here sends.
//
// - Edit: every change of To / Subject / Body is a new version of the draft record (who and when are on the row) and
//   a new text revision (rev). A draft that is with the owner, was sent, or may have been sent cannot be edited.
// - Submit for approval: one text revision of the draft becomes one row in 'Agent Approvals', the same record the
//   deal agent's propose_message creates, with the same Telegram card (Approve / Reject). The owner-only check, the
//   emergency stop, the opt-out list, the idempotency key and the AGENT_MAIL_LIVE switch are all applied by the one
//   existing decision path (lib/dealagent.ts decide -> lib/sendguard.ts guardedSend). No new sending path exists.
// - The approval id is derived from deal + draft + text revision + recipient, so the guard's idempotency key
//   (approval:<id>) is one per deal, recipient and draft version, and submitting the same version twice finds the
//   same approval instead of creating a second one.
import crypto from "node:crypto";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { clean, DRAFT_STATUS, readDeal, saveRecord, type DealRecord } from "@/lib/deal";
import { APPROVALS, approvalCard, decide, emailsIn, recipientTrust, WEB_FLAG, type Io } from "@/lib/dealagent";
import { claim } from "@/lib/claims";
import { DEFAULT_WS } from "@/lib/auth";
import { mailReady } from "@/lib/mailer";

const now = () => new Date().toISOString();
// states in which the text must not change: with the owner, sent, or possibly sent
export const LOCKED = new Set(["submitted", "sent", "delivery_unknown"]);
const CONTENT = ["to_name", "to_email", "subject", "body", "language", "from_role", "from_name", "channel", "why"] as const;
export const NOT_ON_PARTY = "address entered on the draft, not on a party of this deal";

export const draftApprovalId = (dealId: string, draftId: string, rev: number, to: string) =>
  "D" + crypto.createHash("sha256").update(`${dealId}\n${draftId}\n${rev}\n${String(to).trim().toLowerCase()}`).digest("hex").slice(0, 15).toUpperCase();

const latestDraft = (records: DealRecord[], draftId: string) =>
  records.filter((x) => x.kind === "draft" && x.record_id === draftId).sort((a, b) => b.version - a.version)[0];

async function approvalRows(): Promise<string[][]> {
  return (await readRanges(ENGINE_SHEET, [`'${APPROVALS}'!A2:F20000`]).catch(() => null))?.[0] || [];
}
/** The live state of each approval (its latest row): what the deal screen shows next to a submitted draft. */
export async function approvalStates(ids: string[]): Promise<Record<string, { state: string; at: string; mail_id: string; error: string }>> {
  const want = new Set(ids.filter(Boolean)), out: Record<string, { state: string; at: string; mail_id: string; error: string }> = {};
  if (!want.size) return out;
  for (const r of await approvalRows()) {
    if (!want.has(r[0])) continue;
    let j: Record<string, unknown> = {}; try { j = JSON.parse(r[5] || "{}"); } catch { j = {}; }
    out[r[0]] = { state: r[4] || "", at: r[3] || "", mail_id: String(j.mail_id || out[r[0]]?.mail_id || ""), error: String(j.error || "") };
  }
  return out;
}

type Fail = { ok: false; status: number; error: string; code?: string };
/** A new version of a draft from the deal screen. data: the edited fields (merged onto the current version). */
export async function saveDraftEdit(o: { dealId: string; ws: string; by: string; draftId?: string; data: Record<string, unknown> }):
  Promise<{ ok: true; record_id: string; version: number; rev: number; unchanged?: boolean } | Fail> {
  const cur = await readDeal(o.dealId, o.ws);
  const recordId = String(o.draftId || `D${Date.now().toString(36).toUpperCase()}`).slice(0, 60);
  const prev = latestDraft(cur.records, recordId);
  if (prev && LOCKED.has(prev.status)) return { ok: false, status: 409, code: "draft_locked", error: prev.status === "submitted" ? "This draft is waiting for the owner's decision. It cannot be changed now; the owner can reject it first." : "This draft was sent or may have been sent. It cannot be changed; write a new draft." };
  const merged = { ...(prev?.data || {}), ...(o.data || {}) };
  const c = clean("draft", merged);
  if (!c.ok) return { ok: false, status: 400, error: c.error };
  const changed = !prev || CONTENT.some((k) => String(prev.data[k] ?? "") !== String(c.data[k] ?? ""));
  if (prev && !changed && String(o.data?.status || "") === "") return { ok: true, record_id: recordId, version: prev.version, rev: Number(prev.data.rev) || 1, unchanged: true };
  const rev = !prev ? 1 : (Number(prev.data.rev) || 1) + (changed ? 1 : 0);
  // a new text is a new draft for approval purposes: the earlier approval (rejected, refused) stays on the old text
  const status = changed ? ((DRAFT_STATUS as readonly string[]).includes(String(o.data?.status || "")) ? String(o.data.status) : "awaiting_owner_approval") : c.status;
  const data: Record<string, unknown> = { ...c.data, rev, edited_by: o.by, edited_at: now() };
  if (!changed && prev?.data.approval) data.approval = prev.data.approval;
  const version = (prev?.version || 0) + 1;
  await saveRecord(o.dealId, "draft", recordId, version, status, data, o.by, changed && prev ? `edited, text revision ${rev}` : prev ? "status" : "created", o.ws);
  return { ok: true, record_id: recordId, version, rev };
}

export type SubmitResult = { ok: true; approval_id: string; state: string; duplicate: boolean; rev: number } | Fail;
/** Turns the current text revision of one draft into a pending approval (Agent Approvals) and sends the owner the
 *  card. chat: the owner's linked Telegram chat, where Approve / Reject are pressed. */
export async function submitDraft(io: Io, o: { dealId: string; draftId: string; ws: string; by: string; chat: string; lang: "he" | "en"; kindLabel: string }): Promise<SubmitResult> {
  const cur = await readDeal(o.dealId, o.ws);
  const d = latestDraft(cur.records, o.draftId);
  if (!d) return { ok: false, status: 404, error: "draft not found on this deal" };
  const m0 = d.data, rev = Number(m0.rev) || 1, to = String(m0.to_email || "").trim();
  const addrs = emailsIn(to);
  if (addrs.length !== 1 || to.toLowerCase().split(addrs[0]).join("").replace(/[\s<>]/g, "")) return { ok: false, status: 400, code: "no_address", error: "A draft needs exactly one e-mail address in To before it can be submitted." };
  if (!String(m0.subject || "").trim() || !String(m0.body || "").trim()) return { ok: false, status: 400, error: "A draft needs a subject and a body." };
  const id = draftApprovalId(o.dealId, o.draftId, rev, addrs[0]);
  const existing = async () => { const rows = (await approvalRows()).filter((r) => r[0] === id); return rows.length ? rows[rows.length - 1][4] || "pending" : ""; };
  let st = await existing();
  if (st) return { ok: true, approval_id: id, state: st, duplicate: true, rev };
  if (d.status === "sent" || d.status === "delivery_unknown") return { ok: false, status: 409, code: "draft_locked", error: "This draft was sent or may have been sent. Write a new draft." };
  if (!o.chat) return { ok: false, status: 409, code: "no_owner_chat", error: "No owner Telegram chat is linked, so the approval request could not reach the owner. Nothing was created." };
  const lock = await claim(`draftsubmit:${id}`, 120_000);
  if (!lock.ok) return { ok: true, approval_id: id, state: "pending", duplicate: true, rev };
  try {
    st = await existing();
    if (st) return { ok: true, approval_id: id, state: st, duplicate: true, rev };
    // the recipient: on a party of this deal a person saved = known; otherwise the owner's card says where it came from
    const trust = recipientTrust(addrs[0], [], cur.records.filter((y) => y.kind === "party"));
    const m = { from_role: String(m0.from_role || ""), to_name: String(m0.to_name || ""), to_email: addrs[0], language: String(m0.language || ""), subject: String(m0.subject || ""), body: String(m0.body || ""),
      why: String(m0.why || ""), ...(trust === "web" ? { unverified: WEB_FLAG } : trust === "unknown" ? { unverified: NOT_ON_PARTY } : {}), kind_label: o.kindLabel, submitted_by: o.by,
      deal_id: o.dealId, draft_id: o.draftId, draft_rev: rev, ws: o.ws || DEFAULT_WS, lang: o.lang };
    await appendRow(APPROVALS, [id, `draft:${o.dealId}:${o.draftId}`, o.chat, now(), "pending", JSON.stringify(m)]);
    await saveRecord(o.dealId, "draft", o.draftId, d.version + 1, "submitted", { ...m0, rev, approval: { id, state: "pending", submitted_by: o.by, submitted_at: now(), kind_label: o.kindLabel } }, o.by, `submitted for approval ${id}`, o.ws);
    await approvalCard(io, o.chat, id, m, o.lang === "he", o.dealId).catch(() => {});
    return { ok: true, approval_id: id, state: "pending", duplicate: false, rev };
  } finally { await lock.release(); }
}

// ---- staging drill ------------------------------------------------------------------------------------------
// Proof on a staging copy that a submitted draft runs the real decision path and that nothing can leave there. Runs
// only on a preview / server-test copy with mail OFF (mailReady() false), on the fixed TEST deal below; anywhere else it
// refuses before doing anything. The drill's own approver is used only after the real owner check has refused the
// drill identity, and only under those same conditions; with mail off the mailer is never reached with a live mailbox.
export const DRILL_DEAL = "TEST-STAGING-DRAFT-DRILL";
export const drillAllowed = () => (process.env.VERCEL_ENV === "preview" || process.env.DESK_ENV === "server-test") && !mailReady();
export async function stagingDraftDrill(realApprover: (email: string) => Promise<boolean>) {
  if (!drillAllowed()) return { ran: false, reason: "only on a staging copy with mail off" };
  const ws = DEFAULT_WS, by = "staging-drill@example.test", log: string[] = [];
  const io: Io = { send: async (_c, text) => { log.push(text.replace(/<[^>]+>/g, "").slice(0, 160)); }, kick: async () => {} };
  const a = await saveDraftEdit({ dealId: DRILL_DEAL, ws, by, data: { to_name: "Drill Supplier (TEST)", to_email: "drill-supplier@example.test", subject: "[TEST] capability inquiry drill", body: "TEST ONLY. Staging drill of the draft approval flow. Never sent.", why: "staging drill" } });
  if (!a.ok) return { ran: true, error: a.error };
  const b = await saveDraftEdit({ dealId: DRILL_DEAL, ws, by, draftId: a.record_id, data: { body: "TEST ONLY. Staging drill of the draft approval flow (edited). Never sent." } });
  if (!b.ok) return { ran: true, error: b.error };
  const s1 = await submitDraft(io, { dealId: DRILL_DEAL, draftId: a.record_id, ws, by, chat: "staging-drill", lang: "en", kindLabel: "capability inquiry (qualification), not an RFQ" });
  const s2 = await submitDraft(io, { dealId: DRILL_DEAL, draftId: a.record_id, ws, by, chat: "staging-drill", lang: "en", kindLabel: "capability inquiry (qualification), not an RFQ" });
  if (!s1.ok) return { ran: true, error: s1.error };
  const rowsOf = async () => (await approvalRows()).filter((r) => r[0] === s1.approval_id).map((r) => r[4]);
  const afterSubmit = await rowsOf();
  // 1. the real owner check, with the drill identity: must refuse, nothing moves
  await decide({ ...io, approver: realApprover }, "staging-drill", s1.approval_id, true, false, by);
  const afterRealCheck = await rowsOf();
  // 2. the drill approver (staging + mail off only) through the same decide -> guardedSend path
  await decide({ ...io, approver: async () => drillAllowed() }, "staging-drill", s1.approval_id, true, false, "staging-drill (preview only, mail off)");
  const afterApprove = await rowsOf();
  const d = latestDraft((await readDeal(DRILL_DEAL, ws)).records, a.record_id);
  const guard = ((await readRanges(ENGINE_SHEET, ["'Send Guard'!A1:K50000"]).catch(() => null))?.[0] || []).filter((r) => r[2] === `approval:${s1.approval_id}`).map((r) => `${r[3]}${r[10] ? " (" + r[10] + ")" : ""}`);
  return { ran: true, deal_id: DRILL_DEAL, draft_id: a.record_id, versions: [a.version, b.version], text_revision: b.rev, approval_id: s1.approval_id,
    first_submit: s1.state, second_submit: s2.ok ? `${s2.state}, duplicate=${s2.duplicate}, same id=${s2.approval_id === s1.approval_id}` : s2.error,
    approval_rows_after_submit: afterSubmit, after_real_owner_check: afterRealCheck, after_drill_approve: afterApprove, send_guard: guard,
    draft_status: d?.status, draft_approval: d?.data.approval, mail_can_send: mailReady(), messages: log };
}
