// Mission-level approval. Today the owner approves every message (lib/mandate.ts decideSend, lib/sendguard.ts). A
// mission mandate is ONE approval of a bounded job, for example "request quotations for 316L coil from mills in
// Turkey and India, at most 15 recipients, at most 2 messages each, until Friday": what may be stated, and what may
// never be promised.
//
// THIS FILE DECIDES, IT DOES NOT SEND. mayAutoSend is a pure function and nothing calls it: it is not wired to
// lib/sendguard.ts, the outbox or any route. Wiring it is the owner's explicit decision later. Until MISSION_AUTOSEND=1
// it answers {auto: false} for every input, so even a caller added by mistake changes nothing.
//
// It reuses the conversation mandate's vocabulary (lib/mandate.ts): the channel and status types, the address
// normaliser, the proposed-message shape with its extracted facts, and the commitment patterns (textCommitments), and
// adds a wider detector on top. A mission can only narrow what goes without the owner: every doubt is {auto: false}
// with the reason, and the message goes to the owner as it does today.
import { createHash } from "crypto";
import { normAddress, textCommitments, type CommitmentKind, type MandateChannel, type MandateStatus, type ProposedMessage } from "@/lib/mandate";

export const missionAutoSendOn = () => process.env.MISSION_AUTOSEND === "1";

// What no mission can permit. The list is fixed in code; a mission may add to it (never_promise_extra), not remove.
export const NEVER_PROMISE = ["price acceptance", "quantity commitment", "exclusivity", "signature", "payment"] as const;

export type OutreachMission = {
  id: string; version: number; workspace: string;
  product_spec: string; // what is asked about, e.g. "316L stainless coil, 1.5 to 3 mm, 2B finish"
  purpose: string; // e.g. "request for quotation"
  allowed_countries: string[]; allowed_regions: string[]; // a recipient must match one of them by name
  max_recipients: number; max_messages_per_recipient: number;
  channels: MandateChannel[];
  may_state: string[]; // the statements about us and about the need that a message may make, each a short line
  never_promise_extra: string[]; // further words or phrases that must not appear, on top of NEVER_PROMISE
  valid_until: string; // ISO time; at or after it the mission is expired
  status: MandateStatus; status_reason: string;
  approved_by: string; approved_at: string; approved_scope: string; // approved_scope: hash of the scope the owner approved
};
export type OutreachMissionInput = Pick<OutreachMission, "id" | "workspace" | "product_spec" | "purpose" | "max_recipients" | "max_messages_per_recipient" | "valid_until">
  & Partial<Pick<OutreachMission, "allowed_countries" | "allowed_regions" | "channels" | "may_state" | "never_promise_extra">>;

const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x) => typeof x === "string").map((x) => (x as string).trim()).filter(Boolean) : []);
const low = (s: unknown) => String(s ?? "").trim().toLowerCase().replace(/\s+/g, " ");
const CHANNELS: MandateChannel[] = ["email", "linkedin", "whatsapp", "telegram"];
/** Hash of everything the approval covers. Any change of scope after the approval makes the approval void. */
export function missionScope(m: OutreachMission): string {
  return createHash("sha256").update(JSON.stringify([m.id, m.version, m.workspace, m.product_spec, m.purpose, [...m.allowed_countries].map(low).sort(), [...m.allowed_regions].map(low).sort(), m.max_recipients, m.max_messages_per_recipient,
    [...m.channels].sort(), m.may_state.map(low), m.never_promise_extra.map(low), m.valid_until])).digest("hex");
}
export function createMission(i: OutreachMissionInput): OutreachMission {
  return { id: String(i.id || "").trim(), version: 1, workspace: String(i.workspace || "").trim(), product_spec: String(i.product_spec || "").trim(), purpose: String(i.purpose || "").trim(),
    allowed_countries: strs(i.allowed_countries), allowed_regions: strs(i.allowed_regions), max_recipients: i.max_recipients, max_messages_per_recipient: i.max_messages_per_recipient,
    channels: strs(i.channels) as MandateChannel[], may_state: strs(i.may_state), never_promise_extra: strs(i.never_promise_extra), valid_until: String(i.valid_until || ""),
    status: "draft", status_reason: "", approved_by: "", approved_at: "", approved_scope: "" };
}
export function validateMission(m: OutreachMission): string[] {
  const e: string[] = [];
  if (!m.id) e.push("id is required");
  if (!m.workspace) e.push("workspace is required");
  if (!m.product_spec) e.push("product or specification is required");
  if (!m.purpose) e.push("purpose is required");
  if (!m.allowed_countries.length && !m.allowed_regions.length) e.push("at least one allowed country or region is required");
  if (!(Number.isInteger(m.max_recipients) && m.max_recipients >= 1)) e.push("max_recipients must be a whole number, 1 or more");
  if (!(Number.isInteger(m.max_messages_per_recipient) && m.max_messages_per_recipient >= 1)) e.push("max_messages_per_recipient must be a whole number, 1 or more");
  if (!m.channels.length || m.channels.some((c) => !CHANNELS.includes(c))) e.push("channels must name at least one known channel");
  if (!m.may_state.length) e.push("what may be stated is required: without it every statement is outside the mission");
  if (!Number.isFinite(Date.parse(m.valid_until))) e.push("valid_until must be a date and time");
  return e;
}
export type MissionResult = { ok: true; mission: OutreachMission } | { ok: false; errors: string[] };
/** The owner approves this exact scope, once. `by` is the human owner's identity; the caller is responsible for checking it. */
export function approveMission(m: OutreachMission, by: string, nowMs: number): MissionResult {
  const errors = validateMission(m);
  if (!String(by || "").trim()) errors.push("approved_by is required");
  if (m.status !== "draft") errors.push(`only a draft can be approved (status is ${m.status})`);
  if (Number.isFinite(Date.parse(m.valid_until)) && nowMs >= Date.parse(m.valid_until)) errors.push("valid_until is already in the past");
  if (errors.length) return { ok: false, errors };
  return { ok: true, mission: { ...m, status: "approved", status_reason: "", approved_by: String(by).trim(), approved_at: new Date(nowMs).toISOString(), approved_scope: missionScope(m) } };
}
export function revokeMission(m: OutreachMission, reason: string): OutreachMission {
  return { ...m, status: "revoked", status_reason: String(reason || "revoked").slice(0, 200) };
}
/** The status that applies at `nowMs`: an approved mission past valid_until counts as expired even if nobody stored that. */
export function missionStatus(m: OutreachMission, nowMs: number): MandateStatus {
  if (m.status === "approved" && !(nowMs < Date.parse(m.valid_until))) return "expired";
  return m.status;
}

// ---- commitment language -----------------------------------------------------------------------------------
// Deliberately wide. A false alarm costs one look by the owner; a miss could bind the firm. So plain words are
// caught wherever they stand ("what terms do you accept?" is caught too), and the detector only vouches for Latin
// script: a message with letters of another script is never automatic.
const WIDE: [string, RegExp][] = [
  ["accept", /\baccept(s|ed|ing|able|ance)?\b/i],
  ["agree", /\b(agree(s|d|ing|ment)?|agreeable)\b/i],
  ["confirm_order", /\b(confirm\w*|plac(e|ing) (an?|the|our|this)|book(ing)?)\b[^.?!\n]{0,20}\b(orders?|purchase|booking)\b|\b(firm|purchase) order\b|\border (is )?confirmed\b|\b(we|i)('ll| will| shall)? (hereby )?confirm\b/i],
  ["pay", /\b(we|i)\s*('ll|'d| will| shall| would| can| could| are (ready|happy|willing) to)?\s*(pay|prepay|wire|remit|transfer|settle)\b|\b(pre-?payment|down ?payment|advance payment|deposit|letter of credit|l\/c|payment (has been|was|is|will be) (sent|made|arranged))\b/i],
  ["exclusive", /\b(exclusiv\w*|sole (agent|distributor|buyer|supplier)|only (buy|source) from you)\b/i],
  ["sign", /\b(sign(s|ed|ing)?|countersign\w*|signature|execute the (contract|agreement))\b/i],
  ["guarantee", /\b(guarante\w*|guaranty|warrant(y|ies|ed)?|assur(e|ed|ance) you)\b/i],
  ["commit", /\b(commit(s|ted|ting|ment)?|binding|undertak(e|es|ing)|promis(e|es|ed|ing)|you have (a|our) (deal|word)|it'?s a deal|deal is done)\b/i],
  ["quantity", /\b(we|i)\s*('ll|'d| will| shall| would| are going to| intend to| plan to)?\s*(buy|order|purchase|take|procure)\b[^.?!\n]{0,40}\d/i],
  // a number next to words of assent: "USD 640 per tonne works for us", "ok at 640", "let's go with 500 tonnes"
  ["price_acceptance", /\b(ok|okay|fine|acceptable|works( for us| well)?|go ahead|proceed|let'?s (do|go|proceed)|happy with|we('ll| will)? take)\b[^?!\n]{0,40}\d|\d[^?!\n]{0,40}\b((is|are|sounds|looks|seems) (ok|okay|fine|good|great|acceptable|right)|works( for us)?|go ahead|proceed|happy with)\b/i],
];
/** Every kind of commitment wording found in a text; empty when none. Conservative: see the note above. */
export function commitmentLanguage(text: string): string[] {
  const t = String(text || ""), out = new Set<string>();
  for (const k of textCommitments(t) as CommitmentKind[]) out.add(`mandate:${k}`);
  for (const [k, re] of WIDE) if (re.test(t)) out.add(k);
  return [...out];
}
const NON_LATIN = /[^\p{Script=Latin}\p{Script=Common}\p{Script=Inherited}]/u;

// ---- the decision ------------------------------------------------------------------------------------------
// What each sentence rests on, as lib/pipeline.ts drafts carry it: "note:<n>" (a fact of the checked account note or
// relationship card), "brief:<line>" or "claim:<line>" (a statement about us or the need; the line must be one of the
// mission's may_state lines), "question", "courtesy".
export type MissionProposal = {
  message: ProposedMessage; // recipient, channel, subject, text, attachments, extracted facts (lib/mandate.ts)
  recipient_country: string; recipient_region?: string;
  sentences: { text: string; rests_on: string }[]; // must cover the whole text
  evidence: { verdict: string; issues: string[]; writer_run: string; checker_run: string };
};
// What already happened under this mission. last_inbound: what the message answers. "none": nothing came in (a first
// message or a follow-up to silence). "expected": the answer the mission asked for (a quotation, the details asked).
// "unexpected": anything else. "negative": a refusal, a complaint, an opt-out. The caller classifies; unknown = not automatic.
export type MissionHistory = { sent: { recipient: string }[]; last_inbound: "none" | "expected" | "unexpected" | "negative"; opt_out?: boolean };
export type AutoDecision = { auto: true } | { auto: false; reason: string; reasons: string[] };

const squash = (s: string) => String(s || "").replace(/\s+/g, " ").trim();
const words = (s: string) => squash(s).split(" ").filter(Boolean).length;

/** May this message go without the owner looking at it? Only when every condition holds; the first failing one is the reason. */
export function mayAutoSend(mission: OutreachMission | null | undefined, p: MissionProposal, history: MissionHistory, nowMs: number): AutoDecision {
  const no = (reasons: string[]): AutoDecision => ({ auto: false, reason: reasons[0], reasons });
  if (!missionAutoSendOn()) return no(["mission auto-send is off"]);
  const r: string[] = [];
  const m = mission || null, msg = p?.message, text = String(msg?.text || ""), facts = msg?.facts || {};
  if (!m) return no(["no mission"]);
  if (!msg || !squash(text)) return no(["empty message"]);

  // 1. the mission: approved by the owner, unchanged since, not expired
  const status = missionStatus(m, nowMs);
  if (status === "expired") r.push("mission expired");
  else if (status !== "approved") r.push(`mission not approved (status is ${status})`);
  if (!String(m.approved_by || "").trim() || !m.approved_at) r.push("mission has no recorded approval by the owner");
  else if (m.approved_scope !== missionScope(m)) r.push("mission changed after it was approved");
  if (validateMission(m).length) r.push("mission is not valid");

  // 2. the recipient: an allowed place, an allowed channel, under both caps
  const to = normAddress(msg.recipient), country = low(p.recipient_country), region = low(p.recipient_region);
  if (!to) r.push("no recipient");
  if (!(country && m.allowed_countries.some((c) => low(c) === country)) && !(region && m.allowed_regions.some((x) => low(x) === region))) r.push("recipient is outside the allowed countries");
  if (!m.channels.includes(msg.channel)) r.push("channel is not allowed by the mission");
  if (!history || !Array.isArray(history.sent)) r.push("history is missing");
  else {
    const sent = history.sent.map((s) => normAddress(s?.recipient)).filter(Boolean), toThis = sent.filter((a) => a === to).length;
    if (toThis >= m.max_messages_per_recipient) r.push(`message cap for this recipient reached (${toThis} of ${m.max_messages_per_recipient})`);
    if (toThis === 0 && new Set(sent).size >= m.max_recipients) r.push(`recipient cap reached (${new Set(sent).size} of ${m.max_recipients})`);
  }

  // 3. the evidence check: a pass with zero issues, by a run that is not the writer's
  const ev = p.evidence;
  if (!ev || ev.verdict !== "pass") r.push(`evidence verdict is ${ev?.verdict || "missing"}, not pass`);
  else if (!Array.isArray(ev.issues) || ev.issues.length) r.push("evidence check left open issues");
  if (ev && (!ev.writer_run || !ev.checker_run || ev.writer_run === ev.checker_run)) r.push("the check is not by a separate run from the writer");

  // 4. the text: no commitment wording, nothing the extracted facts flag
  const whole = `${msg.subject || ""}\n${text}`;
  if (NON_LATIN.test(whole)) r.push("text is not in Latin script: the commitment detector cannot vouch for it");
  const commit = commitmentLanguage(whole);
  if (commit.length) r.push(`commitment language (${commit.join(", ")}): ${NEVER_PROMISE.join(", ")} are the owner's decision`);
  const extra = m.never_promise_extra.filter((x) => low(whole).includes(low(x)));
  if (extra.length) r.push(`the mission forbids promising: ${extra.join(", ")}`);
  if ((facts.commitments || []).length) r.push("the draft step reported a commitment");
  if ((facts.counterparty_requests || []).length) r.push("the counterparty asked for a commitment");
  if ((facts.actions || []).length) r.push("the draft asks for an action beyond sending text");
  if (facts.flags?.sanctions || facts.flags?.legal) r.push("sanctions or legal flag");
  if ((facts.new_parties || []).length) r.push("a party outside the mission is involved");
  if ((facts.prices || []).length) r.push("the message states a price");
  if ([...strs(msg.attachments), ...strs(facts.attachments)].length) r.push("attachments are not covered by a mission");

  // 5. every sentence inside "what may be stated"
  const sentences = Array.isArray(p.sentences) ? p.sentences : [];
  if (!sentences.length || squash(sentences.map((s) => s?.text || "").join(" ")) !== squash(text)) r.push("the sentences with their basis do not cover the whole text");
  const outside: string[] = [];
  for (const s of sentences) {
    const basis = String(s?.rests_on || "").trim(), t = squash(s?.text || ""), kind = basis.split(":")[0].toLowerCase(), ref = low(basis.slice(kind.length + 1));
    const inside = (kind === "note" && /^\d+$/.test(ref)) // a fact about the counterparty, covered by the evidence check
      || ((kind === "brief" || kind === "claim") && !!ref && m.may_state.some((x) => low(x) === ref))
      || (basis.toLowerCase() === "question" && /\?$/.test(t))
      // a greeting or thanks: short and without figures, so a statement cannot hide behind the label
      || (basis.toLowerCase() === "courtesy" && words(t) <= 12 && !/\d/.test(t));
    if (!inside) outside.push(t.slice(0, 60));
  }
  if (outside.length) r.push(`statement outside what may be stated: "${outside[0]}"`);
  if (strs(facts.claims_used).some((c) => !m.may_state.some((x) => low(x) === low(c)))) r.push("statement outside what may be stated: a claim the mission does not list");

  // 6. what the message answers
  if (history?.opt_out || facts.opt_out_detected) r.push("the counterparty asked not to be contacted");
  if (history?.last_inbound === "negative") r.push("reply to a negative response");
  else if (history?.last_inbound === "unexpected") r.push("reply to an unexpected response");
  else if (history?.last_inbound !== "none" && history?.last_inbound !== "expected") r.push("what the message answers is not known");

  return r.length ? no(r) : { auto: true };
}
