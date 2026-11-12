// Deal drafts connected to the existing approve-and-send flow (lib/draftsend.ts -> lib/dealagent.ts decide ->
// lib/sendguard.ts). Real deal records, approvals, owner check and send guard over an in-memory sheet; only the
// mailer is a recording stand-in (tests/mocks/mailer.ts). Nothing leaves the process.
import { TABS } from "./mocks/sheets-isolation";
import { MAIL } from "./mocks/mailer";
import { draftHistory, readDeal } from "@/lib/deal";
import { draftApprovalId, saveDraftEdit, submitDraft, approvalStates, NOT_ON_PARTY } from "@/lib/draftsend";
import { decide, type Io } from "@/lib/dealagent";
import { isOwner } from "@/lib/telegram";
import { addSuppression } from "@/lib/outreach/suppression";
import { sheetsStore } from "@/lib/outreach/store-sheets";
import { saveRecord } from "@/lib/deal";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
process.env.SEND_APPROVERS = "owner@sinder.test";
process.env.TEAM_USER = "team";
const user = (email: string, role: string, status: string, ws = "") => [email, email, role, status, "", "password", "", "", "", "", "", "", ws];
TABS["Users"] = [user("owner@sinder.test", "admin", "active"), user("second@sinder.test", "admin", "active"), user("analyst@sinder.test", "analyst", "active")];
const cards: { chat: string; text: string; extra?: Record<string, unknown> }[] = [];
const io: Io = { send: async (chat, text, extra) => { cards.push({ chat, text, extra }); }, kick: async () => {}, approver: (e) => isOwner(e) };
const WS = "sinder", DEAL = "TED-TEST-1", CHAT = "C-OWNER", LABEL = "capability inquiry (qualification), not an RFQ";
const approvals = (id: string) => (TABS["Agent Approvals"] || []).filter((r) => r[0] === id).map((r) => String(r[4]));
const draft = async (id: string) => (await readDeal(DEAL, WS)).records.find((x) => x.kind === "draft" && x.record_id === id)!;
const submit = (draftId: string, by = "analyst@sinder.test") => submitDraft(io, { dealId: DEAL, draftId, ws: WS, by, chat: CHAT, lang: "en", kindLabel: LABEL });
const base = { to_name: "Cable Works Ltd", to_email: "sales@cableworks.example", subject: "Capability inquiry: MV cable", body: "Dear team, could you confirm whether you manufacture ...", why: "qualification" };

(async () => {
  // ---- edit versioning
  const a = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "analyst@sinder.test", data: base });
  ok(a.ok && a.version === 1 && a.rev === 1, "a new draft is version 1, text revision 1");
  const id1 = a.ok ? a.record_id : "";
  const b = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "second@sinder.test", draftId: id1, data: { body: "Dear team, please confirm (edited) ..." } });
  ok(b.ok && b.version === 2 && b.rev === 2, "an edit of the body is a new version and a new text revision");
  const h = await draftHistory(DEAL, WS);
  ok(h.length === 2 && h[0].by === "second@sinder.test" && h[1].by === "analyst@sinder.test" && !!h[0].time && h[0].rev === 2, "the history keeps both versions with who and when, newest first");
  const c = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "second@sinder.test", draftId: id1, data: { body: "Dear team, please confirm (edited) ..." } });
  ok(c.ok && c.unchanged === true && (await draftHistory(DEAL, WS)).length === 2, "saving the same text again adds no version");
  const forged = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "x@sinder.test", draftId: id1, data: { subject: "Capability inquiry: MV cable (v3)", status: "sent", sent: true, approval: { id: "DX", state: "sent" } } });
  let d = await draft(id1);
  ok(forged.ok && d.status === "awaiting_owner_approval" && d.data.sent === false && !d.data.approval, "a save cannot mark a draft sent or attach an approval");

  // ---- submit creates exactly one pending approval
  const s1 = await submit(id1);
  const aid = s1.ok ? s1.approval_id : "";
  ok(s1.ok && !s1.duplicate && s1.state === "pending" && approvals(aid).join() === "pending", "submit creates one pending approval in Agent Approvals");
  ok(aid === draftApprovalId(DEAL, id1, 3, base.to_email), "the approval id is per deal + draft + text revision + recipient");
  const row = (TABS["Agent Approvals"] || []).find((r) => r[0] === aid)!;
  const m = JSON.parse(String(row[5]));
  ok(row[2] === CHAT && m.to_email === base.to_email && m.subject.endsWith("(v3)") && m.kind_label === LABEL && m.deal_id === DEAL && m.draft_rev === 3, "the approval carries the submitted text, the label and the deal");
  ok(m.unverified === NOT_ON_PARTY, "an address that is not on a party of the deal is flagged on the owner's card");
  const card = cards.find((x) => JSON.stringify(x.extra || {}).includes(`ag:ok:${aid}`));
  ok(!!card && card.chat === CHAT && card.text.includes(LABEL) && JSON.stringify(card.extra).includes(`ag:no:${aid}`), "the owner gets the same Approve / Reject card, with the label");
  d = await draft(id1);
  ok(d.status === "submitted" && (d.data.approval as { id: string }).id === aid, "the draft shows its approval id and state");
  ok(MAIL.sent.length === 0, "submitting sends nothing");

  // ---- duplicate submit is idempotent
  const cards0 = cards.length;
  const s2 = await submit(id1);
  const [s3, s4] = await Promise.all([submit(id1), submit(id1)]);
  ok(s2.ok && s2.duplicate && s2.approval_id === aid && s3.ok && s4.ok && approvals(aid).length === 1 && cards.length === cards0, "submitting the same version again (also twice at once) creates no second approval and no second card");
  // a fresh draft submitted twice at the same moment
  const f = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "analyst@sinder.test", data: { ...base, to_email: "info@other.example", to_name: "Other" } });
  const fid = f.ok ? f.record_id : "";
  const [p1, p2] = await Promise.all([submit(fid), submit(fid)]);
  const fa = p1.ok ? p1.approval_id : "";
  ok(p1.ok && p2.ok && p2.approval_id === fa && approvals(fa).length === 1, "two simultaneous first submits of one version: one approval row");
  ok((await saveDraftEdit({ dealId: DEAL, ws: WS, by: "analyst@sinder.test", draftId: id1, data: { body: "changed while with the owner" } })).ok === false, "a draft with the owner cannot be edited");

  // ---- non-approver cannot approve (the approver rule of lib/approver.ts, as for the agent's messages)
  MAIL.ready = true;
  await decide(io, CHAT, aid, true, false, "second@sinder.test");
  ok(approvals(aid).join() === "pending" && MAIL.sent.length === 0 && /may not approve/.test(cards[cards.length - 1].text), "another admin (not listed) cannot approve: nothing sent, still pending");
  await decide(io, CHAT, aid, true, false, "team");
  ok(approvals(aid).join() === "pending" && MAIL.sent.length === 0, "the shared team login cannot approve");
  await decide(io, "C-OTHER", aid, true, false, "owner@sinder.test");
  ok(approvals(aid).join() === "pending" && MAIL.sent.length === 0, "another chat cannot decide it");

  // ---- the owner approves: the existing guarded path sends once, the result is on the draft
  await decide(io, CHAT, aid, true, false, "owner@sinder.test");
  d = await draft(id1);
  const ap = d.data.approval as Record<string, string>;
  ok(MAIL.sent.length === 1 && MAIL.sent[0].to === base.to_email && approvals(aid).slice(-1)[0] === "sent", "the owner's approval sends once through the guard");
  ok(d.status === "sent" && d.data.sent === true && ap.state === "sent" && ap.message_id === "<id@x>" && ap.by === "owner@sinder.test", "the draft shows: sent, with the message id and who approved");
  ok((TABS["Send Guard"] || []).filter((r) => r[2] === `approval:${aid}`).map((r) => r[3]).join() === "reserved,sent", "the guard key is approval:<id> (deal + recipient + draft version)");
  const live = await approvalStates([aid]);
  ok(live[aid]?.state === "sent" && live[aid].mail_id === "<id@x>", "read-back of the live approval state for the deal screen");
  await decide(io, CHAT, aid, true, false, "owner@sinder.test");
  ok(MAIL.sent.length === 1, "pressing Approve again sends nothing more");
  const s5 = await submit(id1);
  ok(s5.ok && s5.duplicate && s5.state === "sent" && MAIL.sent.length === 1, "submitting a sent version again returns its state, nothing new");
  ok((await saveDraftEdit({ dealId: DEAL, ws: WS, by: "analyst@sinder.test", draftId: id1, data: { body: "again" } })).ok === false, "a sent draft cannot be edited");

  // ---- reject, then a new text is a new approval
  await decide(io, CHAT, fa, false, false, "owner@sinder.test");
  d = await draft(fid);
  ok(d.status === "rejected" && (d.data.approval as { state: string }).state === "rejected" && MAIL.sent.length === 1, "rejected: the draft shows it, nothing sent");
  const e = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "analyst@sinder.test", draftId: fid, data: { body: "a corrected text" } });
  const s6 = await submit(fid);
  ok(e.ok && e.rev === 2 && s6.ok && !s6.duplicate && s6.approval_id !== fa && approvals(s6.ok ? s6.approval_id : "").join() === "pending", "after a rejection an edited text can be submitted as a new approval");

  // ---- suppression blocks
  await addSuppression({ store: sheetsStore(), now: () => Date.now() }, WS, "@blocked.example", "asked to be removed", "reply", "owner");
  const g = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "analyst@sinder.test", data: { ...base, to_name: "Blocked", to_email: "sales@blocked.example" } });
  const gs = await submit(g.ok ? g.record_id : "");
  const gid = gs.ok ? gs.approval_id : "";
  await decide(io, CHAT, gid, true, false, "owner@sinder.test");
  d = await draft(g.ok ? g.record_id : "");
  ok(MAIL.sent.length === 1 && approvals(gid).slice(-1)[0] === "blocked" && d.status === "refused" && (d.data.approval as { reason: string }).reason === "opted_out", "an opted-out recipient is blocked: nothing sent, the draft shows refused (opted_out)");

  // ---- mail off: nothing leaves, the refusal is recorded
  MAIL.ready = false;
  const k = await saveDraftEdit({ dealId: DEAL, ws: WS, by: "analyst@sinder.test", data: { ...base, to_name: "Off", to_email: "sales@mailoff.example" } });
  const ks = await submit(k.ok ? k.record_id : "");
  const kid = ks.ok ? ks.approval_id : "";
  await decide(io, CHAT, kid, true, false, "owner@sinder.test");
  d = await draft(k.ok ? k.record_id : "");
  ok(MAIL.sent.length === 1 && approvals(kid).slice(-1)[0] === "send_failed" && d.status === "refused" && /mailbox not configured/.test(String((d.data.approval as { error: string }).error)), "mail off: approved but nothing sent; the draft shows refused with the reason");

  // ---- the draft cannot be pushed to a recipient field with two addresses
  await saveRecord(DEAL, "draft", "DBAD", 1, "awaiting_owner_approval", { ...base, to_email: "a@x.example, b@y.example" }, "x", "", WS);
  const bad = await submitDraft(io, { dealId: DEAL, draftId: "DBAD", ws: WS, by: "x", chat: CHAT, lang: "en", kindLabel: LABEL });
  ok(!bad.ok && bad.status === 400, "a To field with two addresses is refused before any approval exists");
  const nochat = await submitDraft(io, { dealId: DEAL, draftId: fid, ws: WS, by: "x", chat: "", lang: "en", kindLabel: LABEL });
  ok(nochat.ok && nochat.duplicate, "an already submitted version still answers without an owner chat");
  process.exit(fail ? 1 : 0);
})();
