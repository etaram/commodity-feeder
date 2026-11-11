// The one door every real e-mail goes through. Both live send paths (the deal agent's approved message in
// lib/dealagent.ts and the panel's Send in app/api/panel/sendmail) call guardedSend; nothing else may call sendMail.
// The checks are plain code, in this order: emergency stop, opt-out list, duplicate key, owner approval reference,
// then a reservation row is written BEFORE the mailer is called, so a crash mid-send is found later as "may have left".
// It reuses the outreach engine's own Suppression tab and emergency stop row (lib/outreach): there is one opt-out list.
import { asWs } from "@/lib/auth";
import { sendMail, type MailResult } from "@/lib/mailer";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { approveMessage, decideSend, messageHash } from "@/lib/mandate";
import { killSwitch as outreachKillSwitch } from "@/lib/outreach/campaign";
import { isSuppressed } from "@/lib/outreach/suppression";
import { cellsToRow, emptySnapshot, sha, TABS, type Row } from "@/lib/outreach/store";
import crypto from "node:crypto";

export const SEND_GUARD = "Send Guard";

export type GuardMessage = { workspace: string; to: string; subject: string; text: string; idempotency_key: string; approved_by: string; approval_ref: string; context: string };
// sent: the server accepted it. send_failed: definitely not sent (refused before any message content left), safe to
// retry after a fix. delivery_unknown: it may have left; never retried automatically, and the owner must look in the
// Sent folder before anything else. refused: a check stopped it before the mailer was called, nothing left.
export type GuardOutcome = "sent" | "send_failed" | "delivery_unknown" | "refused";
export type RefusalReason = "kill_switch" | "opted_out" | "duplicate" | "no_approval" | "invalid" | "checks_unavailable";
export type GuardResult = { outcome: GuardOutcome; reason: RefusalReason | ""; message: string; id: string; error: string; stage: string; prior: string };

export type KeyStatus = "reserved" | "sent" | "send_failed" | "delivery_unknown";
export type KeyMeta = { to: string; subject: string; approved_by: string; approval_ref: string; context: string; detail: string };
export interface SentKeys {
  // The state of a key: null when it was never used.
  status(ws: string, key: string): Promise<KeyStatus | null>;
  // Writes the reservation and says whether this call owns it (false: another call reserved the key first).
  reserve(ws: string, key: string, token: string, at: string, meta: KeyMeta): Promise<boolean>;
  finish(ws: string, key: string, token: string, at: string, status: Exclude<KeyStatus, "reserved">, meta: KeyMeta): Promise<void>;
}
export type GuardDeps = {
  mailer: (m: { to: string; subject: string; text: string }) => Promise<MailResult>;
  // The matching opt-out entry (an address or "@domain"), or null. Throws when the list cannot be read.
  suppressed: (ws: string, email: string) => Promise<string | null>;
  killSwitch: (ws: string) => Promise<boolean>;
  keys: SentKeys;
  now: () => number;
};

// Stages of lib/mailer.ts at which no message content was transmitted yet. Anything else (including a result without
// a stage, or a mailer that throws) counts as "may have left".
const BEFORE_DATA = new Set(["config", "address", "connect", "auth", "mail_from", "rcpt", "data"]);
const ADDRESS = /[^\s@<>,;"']+@[^\s@<>,;"']+\.[a-z]{2,}/gi;
const cut = (v: unknown, n: number) => String(v ?? "").replace(/[\r\n]+/g, " ").slice(0, n);

/** One key state from its rows in written order: the first reservation owns the key until its own result row arrives;
 *  a later reservation counts only after a definite send_failed (the retry). Shared by the Sheets and test stores. */
export function keyState(rows: { status: string; token: string }[]): { status: KeyStatus | null; owner: string } {
  let status: KeyStatus | null = null, owner = "";
  for (const r of rows) {
    if (r.status === "reserved") { if (status === null || status === "send_failed") { status = "reserved"; owner = r.token; } }
    else if (r.token === owner && status === "reserved" && (r.status === "sent" || r.status === "send_failed" || r.status === "delivery_unknown")) status = r.status;
  }
  return { status, owner };
}

export async function guardedSend(deps: GuardDeps, msg: GuardMessage): Promise<GuardResult> {
  const ws = asWs(msg.workspace), key = String(msg.idempotency_key || "").trim().slice(0, 200);
  const res = (outcome: GuardOutcome, reason: RefusalReason | "", message: string, more: Partial<GuardResult> = {}): GuardResult => ({ outcome, reason, message, id: "", error: "", stage: "", prior: "", ...more });
  const to = String(msg.to || "").trim().toLowerCase();
  const addresses = [...new Set(to.match(ADDRESS) || [])];
  if (!addresses.length) return res("refused", "invalid", "refused: no valid recipient address");
  if (!key) return res("refused", "invalid", "refused: no idempotency key");
  let state: KeyStatus | null;
  try {
    // 1. emergency stop  2. opt-out, by address and by domain (every address in the field counts)  3. duplicate key
    if (await deps.killSwitch(ws)) return res("refused", "kill_switch", "stopped: kill switch");
    for (const a of addresses) { const hit = await deps.suppressed(ws, a); if (hit) return res("refused", "opted_out", "stopped: recipient opted out", { error: hit.startsWith("@") ? "domain " + hit : "address" }); }
    state = await deps.keys.status(ws, key);
  } catch (e) {
    // a check that cannot be read is not a pass: nothing is sent until the lists can be read again
    return res("refused", "checks_unavailable", "stopped: the safety checks could not be read", { error: cut((e as Error).message || e, 200) });
  }
  // a reservation without a result is a send that started and never reported back: it may have left
  if (state === "sent" || state === "delivery_unknown" || state === "reserved") return res("refused", "duplicate", "duplicate", { prior: state === "reserved" ? "delivery_unknown" : state });
  // 4. The policy of lib/mandate.ts in its default mode (conversation mode OFF: every message needs the owner). Used
  // here only as an assertion that this message carries an owner approval; it changes nothing about who approves.
  const now = deps.now(), message = { recipient: to, channel: "email" as const, subject: msg.subject, text: msg.text };
  const by = String(msg.approved_by || "").trim(), ref = String(msg.approval_ref || "").trim();
  const approval = by && ref ? approveMessage({ recipient: to, channel: "email", message_hash: messageHash(message), mandate_id: null, mandate_version: null }, by, now) : null;
  const policy = decideSend({ message, conversationMode: false, approval, now });
  if (policy.decision !== "ALLOW") return res("refused", policy.decision === "DENY" ? "invalid" : "no_approval", policy.decision === "DENY" ? "refused: " + policy.reasons.join("; ").slice(0, 200) : "refused: no owner approval reference", { error: policy.reasons.join("; ").slice(0, 200) });
  // 5. Reserve, then send. If the reservation cannot be written, nothing is sent.
  const token = crypto.randomUUID(), meta = (detail: string): KeyMeta => ({ to: cut(to, 200), subject: cut(msg.subject, 200), approved_by: cut(by, 120), approval_ref: cut(ref, 200), context: cut(msg.context, 200), detail: cut(detail, 300) });
  try {
    if (!(await deps.keys.reserve(ws, key, token, new Date(now).toISOString(), meta("")))) return res("refused", "duplicate", "duplicate", { prior: "delivery_unknown" });
  } catch (e) { return res("refused", "checks_unavailable", "stopped: the send could not be recorded", { error: cut((e as Error).message || e, 200) }); }
  let r: MailResult;
  try { r = await deps.mailer({ to, subject: msg.subject, text: msg.text }); } catch (e) { r = { ok: false, error: "the mailer failed without an answer: " + cut((e as Error).message || e, 160) }; }
  const stage = String(r?.stage || ""), error = cut(r?.error || "", 200);
  const outcome: GuardOutcome = r?.ok === true ? "sent" : BEFORE_DATA.has(stage) ? "send_failed" : "delivery_unknown";
  // if this row cannot be written the reservation stays open, which later reads as "may have left": the safe side
  await deps.keys.finish(ws, key, token, new Date(deps.now()).toISOString(), outcome, meta(outcome === "sent" ? String(r.id || "") : `${stage || "unknown stage"}: ${error}`)).catch(() => {});
  if (outcome === "sent") return res("sent", "", "sent", { id: String(r.id || ""), stage });
  if (outcome === "send_failed") return res("send_failed", "", "send_failed: nothing left the system, safe to retry after a fix", { error, stage });
  return res("delivery_unknown", "", "delivery_unknown: the message may have left, check the Sent folder before anything else", { error, stage });
}

/** Idempotency key for a send without a request id: the same recipient, subject and body on the same calendar day. */
export const contentKey = (to: string, subject: string, body: string, day: string) => "content:" + sha(`${String(to).trim().toLowerCase()}\n${subject}\n${body}\n${day}`);

// ---- production dependencies (Sheets) ---------------------------------------------------------------------------
// A tab that does not exist yet is an empty list; any other read failure is an error, so the guard stops the send.
// from: first row to read. Tabs this module creates itself have no header row (appendRow starts at row 1), so they are read from 1.
async function tab(name: string, cols: string, from = 2): Promise<string[][]> {
  try {
    const r = await readRanges(ENGINE_SHEET, [`'${name}'!A${from}:${cols}50000`]);
    if (!r) throw new Error("Sheets is not configured");
    return r[0] || [];
  } catch (e) { if (String((e as Error).message || e).includes("Unable to parse range")) return []; throw e; }
}
const rowsOf = async (name: string): Promise<Row[]> => (await tab(name, "H")).map(cellsToRow).filter((r): r is Row => !!r);

// Rows of 'Send Guard': A time, B ws, C key, D status, E token, F to, G subject, H approved_by, I approval_ref, J context, K detail.
export class SheetsSentKeys implements SentKeys {
  private async rows(ws: string, key: string) { return (await tab(SEND_GUARD, "K", 1)).filter((r) => asWs(r[1]) === ws && r[2] === key).map((r) => ({ status: r[3] || "", token: r[4] || "" })); }
  async status(ws: string, key: string) { return keyState(await this.rows(ws, key)).status; }
  async reserve(ws: string, key: string, token: string, at: string, m: KeyMeta) {
    await appendRow(SEND_GUARD, [at, ws, key, "reserved", token, m.to, m.subject, m.approved_by, m.approval_ref, m.context, m.detail]);
    // Sheets has no atomic write: two calls with one key both append, read back, and the earlier row owns the key
    const s = keyState(await this.rows(ws, key));
    return s.status === "reserved" && s.owner === token;
  }
  async finish(ws: string, key: string, token: string, at: string, status: Exclude<KeyStatus, "reserved">, m: KeyMeta) {
    await appendRow(SEND_GUARD, [at, ws, key, status, token, m.to, m.subject, m.approved_by, m.approval_ref, m.context, m.detail]);
  }
}

/** The live dependencies. Make a new one per send: the lists are read again immediately before every message. */
export function sheetsGuardDeps(over: Partial<GuardDeps> = {}): GuardDeps {
  return {
    mailer: sendMail,
    // the workspace-wide entries ("*": opt-outs and hard bounces) of the outreach Suppression tab
    suppressed: async (ws, email) => isSuppressed({ ...emptySnapshot(), suppression: await rowsOf(TABS.suppression) }, ws, email, "*")?.value || null,
    killSwitch: async (ws) => outreachKillSwitch({ ...emptySnapshot(), campaigns: await rowsOf(TABS.campaigns) }, ws).engaged,
    keys: new SheetsSentKeys(),
    now: () => Date.now(),
    ...over,
  };
}

/** In-memory key store for tests. */
export class MemorySentKeys implements SentKeys {
  rows: { ws: string; key: string; status: string; token: string; meta: KeyMeta }[] = [];
  private of(ws: string, key: string) { return this.rows.filter((r) => r.ws === ws && r.key === key); }
  async status(ws: string, key: string) { return keyState(this.of(ws, key)).status; }
  async reserve(ws: string, key: string, token: string, _at: string, meta: KeyMeta) { this.rows.push({ ws, key, status: "reserved", token, meta }); const s = keyState(this.of(ws, key)); return s.status === "reserved" && s.owner === token; }
  async finish(ws: string, key: string, token: string, _at: string, status: Exclude<KeyStatus, "reserved">, meta: KeyMeta) { this.rows.push({ ws, key, status, token, meta }); }
}
