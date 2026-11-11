// Conversation mandate and the deterministic send policy.
// A mandate is the owner's written permission for one conversation: one counterparty, one verified address, one
// channel, one purpose, with boundaries. decideSend is plain code: no model takes part in the authorization. The
// drafting step may extract facts from a message, but facts can only make the decision stricter, never looser.
// Nothing here sends anything and nothing is wired to dealagent.ts or the outbox yet (see
// docs/release-2026-11-13/CONVERSATION_MANDATES.md). Default: conversation mode OFF, every message needs approval.
import { createHash } from "crypto";

export type MandateChannel = "email" | "linkedin" | "whatsapp" | "telegram";
export type MandateStatus = "draft" | "approved" | "revoked" | "expired";
export type CommitmentKind = "sign" | "guarantee" | "bid" | "pay" | "exclusivity" | "other";
// Side effects that are never authorized by this module, with or without a mandate, with or without an approval.
export type ForbiddenAction = "sign" | "submit_bid" | "move_money";

export type PriceBoundary = { currency: string; min: number; max: number; unit: string };
export type QuantityBoundary = { min: number; max: number; unit: string };

export type Mandate = {
  id: string; version: number; workspace: string;
  counterparty: { legal_name: string; address: string }; // address: the verified channel address (never invented)
  channel: MandateChannel;
  represented_sender: { name: string; org: string; address: string };
  purpose: string; target_outcome: string;
  permitted_claims: string[]; // claim ids the conversation may use
  permitted_topics: string[]; // topic labels inside the purpose; anything else is a new topic
  approved_attachments: string[]; // attachment refs the owner approved
  price_boundary: PriceBoundary | null; // null: no price may be discussed without the owner
  quantity_boundary: QuantityBoundary | null;
  max_concessions: number; max_messages: number;
  expires_at: string; // ISO time; at or after it the mandate is expired
  stop_reasons: string[]; // owner-defined conditions that pause the conversation
  status: MandateStatus; status_reason: string;
  approved_by: string; approved_at: string;
};

export type MandateInput = Omit<Mandate, "version" | "status" | "status_reason" | "approved_by" | "approved_at" | "permitted_topics" | "approved_attachments" | "stop_reasons" | "price_boundary" | "quantity_boundary">
  & Partial<Pick<Mandate, "permitted_topics" | "approved_attachments" | "stop_reasons" | "price_boundary" | "quantity_boundary">>;

export const normAddress = (v: unknown) => String(v ?? "").trim().toLowerCase().replace(/^mailto:/, "");
const sha = (v: string) => createHash("sha256").update(v).digest("hex");
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x) => typeof x === "string").map((x) => (x as string).trim()).filter(Boolean) : []);
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : NaN);

/** Hash of exactly what leaves: recipient, channel, subject, text and attachment refs. Any edit changes it. */
export function messageHash(m: { recipient: string; channel: string; subject?: string; text: string; attachments?: string[] }): string {
  return sha(JSON.stringify([normAddress(m.recipient), String(m.channel || ""), String(m.subject || ""), String(m.text || ""), [...strs(m.attachments)].sort()]));
}

export function validateMandate(m: Mandate): string[] {
  const e: string[] = [];
  if (!m.id) e.push("id is required");
  if (!m.workspace) e.push("workspace is required");
  if (!m.counterparty?.legal_name) e.push("counterparty legal name is required");
  if (!normAddress(m.counterparty?.address)) e.push("counterparty verified address is required");
  if (m.channel === "email" && !/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/.test(normAddress(m.counterparty?.address))) e.push("counterparty address is not an email address");
  if (!m.represented_sender?.name || !m.represented_sender?.org) e.push("represented sender name and organisation are required");
  if (!m.purpose) e.push("purpose is required");
  if (!(Number.isInteger(m.max_messages) && m.max_messages >= 1)) e.push("max_messages must be a whole number, 1 or more");
  if (!(Number.isInteger(m.max_concessions) && m.max_concessions >= 0)) e.push("max_concessions must be a whole number, 0 or more");
  if (!Number.isFinite(Date.parse(m.expires_at))) e.push("expires_at must be a date and time");
  const p = m.price_boundary;
  if (p && !(p.currency && p.unit && Number.isFinite(p.min) && Number.isFinite(p.max) && p.min >= 0 && p.min <= p.max)) e.push("price boundary needs currency, unit and min <= max");
  const q = m.quantity_boundary;
  if (q && !(q.unit && Number.isFinite(q.min) && Number.isFinite(q.max) && q.min >= 0 && q.min <= q.max)) e.push("quantity boundary needs unit and min <= max");
  return e;
}

export function createMandate(input: MandateInput): Mandate {
  return {
    ...input,
    counterparty: { legal_name: String(input.counterparty?.legal_name || "").trim(), address: normAddress(input.counterparty?.address) },
    permitted_claims: strs(input.permitted_claims), permitted_topics: strs(input.permitted_topics),
    approved_attachments: strs(input.approved_attachments), stop_reasons: strs(input.stop_reasons),
    price_boundary: input.price_boundary ?? null, quantity_boundary: input.quantity_boundary ?? null,
    version: 1, status: "draft", status_reason: "", approved_by: "", approved_at: "",
  };
}

export type MandateResult = { ok: true; mandate: Mandate } | { ok: false; errors: string[] };

/** The owner approves this exact version. `by` is the human owner's identity; the caller is responsible for checking it. */
export function approveMandate(m: Mandate, by: string, nowMs: number): MandateResult {
  const errors = validateMandate(m);
  if (!String(by || "").trim()) errors.push("approved_by is required");
  if (m.status !== "draft") errors.push(`only a draft can be approved (status is ${m.status})`);
  if (Number.isFinite(Date.parse(m.expires_at)) && nowMs >= Date.parse(m.expires_at)) errors.push("expiry is already in the past");
  if (errors.length) return { ok: false, errors };
  return { ok: true, mandate: { ...m, status: "approved", status_reason: "", approved_by: String(by).trim(), approved_at: new Date(nowMs).toISOString() } };
}

/** Any change of scope makes a new draft version: the previous approval does not carry over. */
export function amendMandate(m: Mandate, patch: Partial<MandateInput>): Mandate {
  const next = createMandate({ ...m, ...patch, id: m.id, workspace: m.workspace });
  return { ...next, version: m.version + 1 };
}

export function revokeMandate(m: Mandate, reason: string): Mandate {
  return { ...m, version: m.version + 1, status: "revoked", status_reason: String(reason || "revoked").slice(0, 200) };
}

/** The status that applies at `nowMs`: an approved mandate past its expiry counts as expired even if nobody stored that. */
export function effectiveStatus(m: Mandate, nowMs: number): MandateStatus {
  if (m.status === "approved" && !(nowMs < Date.parse(m.expires_at))) return "expired";
  return m.status;
}

// ---- storage (injected; append-only versions, highest version wins) ----------------------------------------
export interface MandateStore {
  put(m: Mandate): Promise<void>;
  versions(workspace: string, id: string): Promise<Mandate[]>;
}
export class MemoryMandateStore implements MandateStore {
  rows: Mandate[] = [];
  async put(m: Mandate) { this.rows.push(JSON.parse(JSON.stringify(m))); }
  async versions(workspace: string, id: string) { return this.rows.filter((r) => r.workspace === workspace && r.id === id).map((r) => JSON.parse(JSON.stringify(r)) as Mandate); }
}
export async function saveMandate(store: MandateStore, m: Mandate): Promise<void> {
  const have = await store.versions(m.workspace, m.id);
  const same = have.find((x) => x.version === m.version);
  if (same) { if (JSON.stringify(same) !== JSON.stringify(m)) throw new Error(`mandate ${m.id} version ${m.version} already exists with different content`); return; }
  await store.put(m);
}
export async function loadMandate(store: MandateStore, workspace: string, id: string): Promise<Mandate | null> {
  return (await store.versions(workspace, id)).sort((a, b) => b.version - a.version)[0] || null;
}

// ---- send policy ------------------------------------------------------------------------------------------
// Facts the drafting step extracted. They are data, never instructions: free text in here (notes, names, topics) is
// only compared against the mandate. Every field can add a reason to stop; none can remove one.
export type MessageFacts = {
  prices?: { amount: number; currency: string; unit: string }[];
  quantities?: { amount: number; unit: string }[];
  commitments?: { kind: CommitmentKind; text?: string }[]; // what our message would commit to
  counterparty_requests?: CommitmentKind[]; // what the other side asked us to commit to
  concessions?: number; // concessions this message makes
  new_parties?: string[]; // any person or company other than the mandate's counterparty
  inbound_from?: string; // the address the last reply came from
  topics?: string[]; claims_used?: string[];
  attachments?: string[]; // attachment refs (merged with message.attachments)
  actions?: ForbiddenAction[]; // side effects the step wants beyond sending text
  flags?: { sanctions?: boolean; legal?: boolean };
  stop_reasons_hit?: string[];
  opt_out_detected?: boolean; // the counterparty asked not to be contacted
  notes?: string[]; // free text, ignored by the policy
};

export type ProposedMessage = { recipient: string; channel: MandateChannel; subject?: string; text: string; attachments?: string[]; facts?: MessageFacts };

// A per-message approval by the owner, bound to the exact message it was given for.
export type MessageApproval = { recipient: string; channel: string; message_hash: string; mandate_id: string | null; mandate_version: number | null; approved_by: string; approved_at: string };

export type SendInput = {
  mandate?: Mandate | null;
  message: ProposedMessage;
  conversation?: { sent_count: number; concessions_made?: number }; // messages already sent in this conversation
  suppression?: string[]; // active entries: exact address or "@domain"
  killSwitch?: boolean;
  conversationMode?: boolean; // feature flag, default false
  approval?: MessageApproval | null;
  now: number; // ms; passed in so the function stays pure
};

export type Decision = "ALLOW" | "REQUIRES_APPROVAL" | "DENY";
export type Bound = { recipient: string; channel: string; message_hash: string; mandate_id: string | null; mandate_version: number | null };
export type SendDecision = { decision: Decision; reasons: string[]; bound: Bound };

// Text backstop: the policy does not rely only on extracted facts. Commitment wording in the text itself escalates.
const COMMIT_PATTERNS: [CommitmentKind, RegExp][] = [
  ["sign", /\b(sign|signed|signing|countersign\w*|signature)\b/i],
  ["guarantee", /\b(guarantee\w*|guaranty|warrant(y|ies|ed)?)\b/i],
  ["bid", /\b(submit\w*|place|lodge|enter)\s+(a|an|the|our|my)?\s*(bid|tender|offer)\b|\b(our|my) (binding )?(bid|tender)\b/i],
  ["pay", /\b(we|i)\s*('ll| will| shall| agree to| can| are ready to)?\s*(pay|prepay|wire|remit|transfer)\b|\b(purchase order|letter of credit|payment (has been|was|is) (sent|made))\b/i],
  ["exclusivity", /\bexclusiv(e|ely|ity)\b/i],
  ["other", /\b(we|i)\s*(hereby\s+)?(accept|agree to|commit to|confirm (the|our|this) order)\b/i],
];
export function textCommitments(text: string): CommitmentKind[] {
  const t = String(text || "");
  return COMMIT_PATTERNS.filter(([, re]) => re.test(t)).map(([k]) => k);
}

export function suppressed(list: string[] | undefined, address: string): boolean {
  const a = normAddress(address);
  if (!a) return false;
  const dom = a.includes("@") ? "@" + a.split("@")[1] : "";
  return strs(list).some((s) => { const v = normAddress(s); return v === a || (!!dom && v === dom); });
}

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

export function decideSend(input: SendInput): SendDecision {
  const msg = input.message;
  const facts: MessageFacts = msg.facts || {};
  const recipient = normAddress(msg.recipient);
  const attachments = [...new Set([...strs(msg.attachments), ...strs(facts.attachments)])];
  const flagOn = input.conversationMode === true;
  const m = input.mandate || null;
  const status = m ? effectiveStatus(m, input.now) : null;
  // The mandate is "in force" only with the flag on and a non-draft status. Otherwise it plays no part.
  const inForce = !!m && flagOn && status !== "draft";
  const bound: Bound = {
    recipient, channel: msg.channel,
    message_hash: messageHash({ recipient, channel: msg.channel, subject: msg.subject, text: msg.text, attachments }),
    mandate_id: inForce ? m!.id : null, mandate_version: inForce ? m!.version : null,
  };
  const out = (decision: Decision, reasons: string[]): SendDecision => ({ decision, reasons, bound });

  // 1. Hard stops. They hold with or without a mandate, flag or approval.
  const deny: string[] = [];
  if (input.killSwitch) deny.push("kill_switch: sending is stopped globally");
  if (!recipient) deny.push("no_recipient");
  if (!String(msg.text || "").trim()) deny.push("empty_message");
  if (suppressed(input.suppression, recipient)) deny.push("recipient_suppressed: the recipient opted out or is on the suppression list");
  if (facts.opt_out_detected === true) deny.push("opt_out: the counterparty asked not to be contacted");
  const actions = (Array.isArray(facts.actions) ? facts.actions : []).filter((a) => a === "sign" || a === "submit_bid" || a === "move_money");
  for (const a of actions) deny.push(`forbidden_action:${a}: signing, submitting a bid and moving money are never done by this system`);
  if (inForce) {
    if (status === "revoked") deny.push("mandate_revoked");
    if (status === "expired") deny.push("mandate_expired");
    if (recipient !== normAddress(m!.counterparty.address)) deny.push("recipient_mismatch: the recipient is not the mandate's verified address");
    if (msg.channel !== m!.channel) deny.push("channel_mismatch: the channel is not the mandate's channel");
  }
  if (deny.length) return out("DENY", deny);

  // 2. Escalations: reasons that need the owner whatever the mandate says.
  const esc: string[] = [];
  const kinds = new Set<CommitmentKind>();
  for (const c of Array.isArray(facts.commitments) ? facts.commitments : []) kinds.add(c?.kind || "other");
  for (const k of textCommitments(`${msg.subject || ""}\n${msg.text}`)) kinds.add(k);
  for (const k of kinds) esc.push(`commitment:${k}: a binding commitment is the owner's decision`);
  for (const k of new Set(Array.isArray(facts.counterparty_requests) ? facts.counterparty_requests : [])) esc.push(`counterparty_requests:${k}: the counterparty asked for a binding commitment`);
  if (facts.flags?.sanctions) esc.push("sanctions_flag");
  if (facts.flags?.legal) esc.push("legal_flag");

  // 3. A per-message approval releases exactly the message it was given for (hard stops above still apply).
  const ap = input.approval || null;
  let approvalOk = false;
  if (ap) {
    if (!String(ap.approved_by || "").trim()) esc.push("approval_invalid: no approver recorded");
    else if (ap.message_hash !== bound.message_hash) esc.push("approval_invalid: message_hash mismatch, the message changed after it was approved");
    else if (normAddress(ap.recipient) !== bound.recipient || ap.channel !== bound.channel) esc.push("approval_invalid: recipient or channel differs from the approved message");
    else if ((ap.mandate_id ?? null) !== bound.mandate_id || (ap.mandate_version ?? null) !== bound.mandate_version) esc.push("approval_invalid: the mandate changed after the message was approved");
    else approvalOk = true;
  }
  if (approvalOk) return out("ALLOW", ["owner_approved_this_message"]);

  // 4. Without a mandate in force, today's rule: every message waits for the owner.
  if (!m) return out("REQUIRES_APPROVAL", ["no_mandate: every message needs the owner's approval", ...esc]);
  if (!flagOn) return out("REQUIRES_APPROVAL", ["conversation_mode_off: every message needs the owner's approval", ...esc]);
  if (status === "draft") return out("REQUIRES_APPROVAL", ["mandate_not_approved: the mandate is still a draft", ...esc]);

  // 5. Mandate boundaries.
  const conv = input.conversation || { sent_count: 0 };
  const sent = Number.isFinite(conv.sent_count) && conv.sent_count >= 0 ? Math.floor(conv.sent_count) : 0;
  if (sent === 0) esc.push("first_message: the first message of a conversation always needs approval");
  if (sent >= m.max_messages) esc.push(`max_messages: ${sent} already sent, the mandate allows ${m.max_messages}`);

  for (const p of Array.isArray(facts.prices) ? facts.prices : []) {
    const b = m.price_boundary, a = num(p?.amount);
    if (!b) esc.push("price_not_permitted: the mandate has no price boundary");
    else if (!Number.isFinite(a) || !same(String(p.currency || ""), b.currency) || !same(String(p.unit || ""), b.unit)) esc.push(`price_basis_mismatch: only ${b.currency} per ${b.unit} is inside the mandate`);
    else if (a < b.min || a > b.max) esc.push(`price_out_of_bounds: ${a} is outside ${b.min} to ${b.max} ${b.currency} per ${b.unit}`);
  }
  for (const q of Array.isArray(facts.quantities) ? facts.quantities : []) {
    const b = m.quantity_boundary, a = num(q?.amount);
    if (!b) esc.push("quantity_not_permitted: the mandate has no quantity boundary");
    else if (!Number.isFinite(a) || !same(String(q.unit || ""), b.unit)) esc.push(`quantity_basis_mismatch: only ${b.unit} is inside the mandate`);
    else if (a < b.min || a > b.max) esc.push(`quantity_out_of_bounds: ${a} is outside ${b.min} to ${b.max} ${b.unit}`);
  }
  const conc = Math.max(0, Number(facts.concessions) || 0) + Math.max(0, Number(conv.concessions_made) || 0);
  if (conc > m.max_concessions) esc.push(`max_concessions: ${conc} would exceed the ${m.max_concessions} allowed`);

  const newParties = strs(facts.new_parties).filter((p) => !same(p, m.counterparty.legal_name) && normAddress(p) !== normAddress(m.counterparty.address));
  if (newParties.length) esc.push("new_party: the conversation involves a party outside the mandate");
  if (facts.inbound_from && normAddress(facts.inbound_from) !== normAddress(m.counterparty.address)) esc.push("party_changed: the reply came from a different address than the mandate's counterparty");
  if (strs(facts.topics).some((t) => !m.permitted_topics.some((x) => same(x, t)))) esc.push("new_topic: a topic outside the mandate's purpose");
  if (strs(facts.claims_used).some((c) => !m.permitted_claims.includes(c))) esc.push("claim_not_permitted: a claim the owner did not approve");
  if (attachments.some((a) => !m.approved_attachments.includes(a))) esc.push("attachment_not_approved");
  const hit = strs(facts.stop_reasons_hit);
  if (hit.length) esc.push(`stop_reason: ${hit.length} owner-defined stop condition(s) met`);

  if (esc.length) return out("REQUIRES_APPROVAL", esc);
  return out("ALLOW", ["within_mandate"]);
}

/** The record of an owner approving one message: built from the decision's bound, so it cannot outlive an edit. */
export function approveMessage(bound: Bound, by: string, nowMs: number): MessageApproval {
  return { ...bound, approved_by: String(by || "").trim(), approved_at: new Date(nowMs).toISOString() };
}
