// The send guard (lib/sendguard.ts): the one door for real e-mail. Everything here runs against injected
// dependencies: a scripted mailer, in-memory lists and key store. No network, no mailbox, nothing is sent.
import { contentKey, guardedSend, keyState, MemorySentKeys, type GuardDeps, type GuardMessage } from "@/lib/sendguard";
import type { MailResult } from "@/lib/mailer";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

function world() {
  const w = {
    calls: [] as { to: string; subject: string }[], script: [] as (MailResult | "throw" | "hang-check")[],
    stop: false, optOut: new Set<string>(), keys: new MemorySentKeys(), listsDown: false, order: [] as string[],
    deps: null as unknown as GuardDeps,
  };
  w.deps = {
    mailer: async (m) => {
      w.order.push("mailer"); w.calls.push({ to: m.to, subject: m.subject });
      const next = w.script.shift();
      if (next === "throw") throw new Error("socket hang up");
      return (next as MailResult) || { ok: true, id: `<m${w.calls.length}@test>`, stage: "done" };
    },
    suppressed: async (_ws, email) => { if (w.listsDown) throw new Error("Sheets 503"); const dom = "@" + email.split("@")[1]; return w.optOut.has(email) ? email : w.optOut.has(dom) ? dom : null; },
    killSwitch: async () => { if (w.listsDown) throw new Error("Sheets 503"); return w.stop; },
    keys: { status: (ws, k) => w.keys.status(ws, k), finish: (...a) => w.keys.finish(...a), reserve: async (...a) => { w.order.push("reserve"); return w.keys.reserve(...a); } },
    now: () => Date.parse("2026-11-11T10:00:00Z"),
  };
  return w;
}
const msg = (over: Partial<GuardMessage> = {}): GuardMessage => ({ workspace: "sinder", to: "buyer@acme.example", subject: "RFQ", text: "Dear team, a request for information.", idempotency_key: "approval:A1", approved_by: "owner@sinder.example", approval_ref: "Agent Approvals:A1", context: "test", ...over });

(async () => {
  // ---- the plain path
  let w = world();
  let r = await guardedSend(w.deps, msg());
  ok(r.outcome === "sent" && w.calls.length === 1 && r.id === "<m1@test>", "an approved message with a fresh key is sent once");
  ok(w.order.join() === "reserve,mailer" && w.keys.rows.map((x) => x.status).join() === "reserved,sent", "the reservation row is written before the mailer is called, then the result");
  ok(w.keys.rows[0].meta.approval_ref === "Agent Approvals:A1" && w.keys.rows[0].meta.approved_by === "owner@sinder.example", "the reservation records who approved and the approval reference");

  // ---- kill switch
  w = world(); w.stop = true;
  r = await guardedSend(w.deps, msg());
  ok(r.outcome === "refused" && r.reason === "kill_switch" && r.message === "stopped: kill switch" && w.calls.length === 0 && w.keys.rows.length === 0, "kill switch engaged: refused, the mailer is not called, nothing is reserved");
  w.stop = false;
  ok((await guardedSend(w.deps, msg())).outcome === "sent", "after the kill switch is cleared the same key can be sent (a refusal uses nothing up)");
  w = world(); w.stop = true; w.optOut.add("buyer@acme.example");
  ok((await guardedSend(w.deps, msg())).reason === "kill_switch", "the kill switch is checked first");

  // ---- opt-out by address and by domain
  w = world(); w.optOut.add("buyer@acme.example");
  r = await guardedSend(w.deps, msg({ to: " Buyer@ACME.example " }));
  ok(r.outcome === "refused" && r.reason === "opted_out" && r.message === "stopped: recipient opted out" && w.calls.length === 0, "an opted-out address is refused (any letter case)");
  w = world(); w.optOut.add("@acme.example");
  r = await guardedSend(w.deps, msg({ to: "someone.else@acme.example" }));
  ok(r.reason === "opted_out" && /domain/.test(r.error) && w.calls.length === 0, "an opted-out domain refuses every address in it");
  ok((await guardedSend(w.deps, msg({ to: "x@other.example", idempotency_key: "k2" }))).outcome === "sent", "another domain is not affected");
  w = world(); w.optOut.add("b@optout.example");
  ok((await guardedSend(w.deps, msg({ to: "a@fine.example; b@optout.example" }))).reason === "opted_out" && w.calls.length === 0, "an opted-out address hidden next to another one is still refused");

  // ---- duplicate key
  w = world();
  await guardedSend(w.deps, msg());
  r = await guardedSend(w.deps, msg());
  ok(r.outcome === "refused" && r.reason === "duplicate" && r.message === "duplicate" && r.prior === "sent" && w.calls.length === 1, "a key already recorded as sent is refused: one mail");
  ok((await guardedSend(w.deps, msg({ workspace: "other-ws" }))).outcome === "sent", "keys are per workspace");
  w = world();
  const both = await Promise.all([guardedSend(w.deps, msg()), guardedSend(w.deps, msg())]);
  ok(w.calls.length === 1 && both.filter((x) => x.outcome === "sent").length === 1 && both.filter((x) => x.reason === "duplicate").length === 1, "two calls with one key at the same moment send one mail");

  // ---- a timeout after DATA started: delivery_unknown, and a retry is refused
  w = world(); w.script.push({ ok: false, error: "SMTP timeout", stage: "body" });
  r = await guardedSend(w.deps, msg());
  ok(r.outcome === "delivery_unknown" && r.stage === "body" && /Sent folder/.test(r.message), "a timeout after the message data started is delivery_unknown, not a failure");
  r = await guardedSend(w.deps, msg());
  ok(r.outcome === "refused" && r.reason === "duplicate" && r.prior === "delivery_unknown" && w.calls.length === 1, "a retry of a delivery_unknown key is refused: the mailer is not called again");
  w = world(); w.script.push({ ok: false, error: "SMTP 451: try later", stage: "body" });
  ok((await guardedSend(w.deps, msg())).outcome === "delivery_unknown", "any error after DATA started is delivery_unknown, whatever the server said");
  w = world(); w.script.push({ ok: false, error: "something odd" });
  ok((await guardedSend(w.deps, msg())).outcome === "delivery_unknown", "a failure without a stage is unknown, never a plain failure");
  w = world(); w.script.push("throw");
  r = await guardedSend(w.deps, msg());
  ok(r.outcome === "delivery_unknown" && (await guardedSend(w.deps, msg())).reason === "duplicate" && w.calls.length === 1, "a mailer that throws is delivery_unknown and is not retried");
  // the process died between the reservation and the result: the open reservation blocks a second send
  w = world(); await w.keys.reserve("sinder", "approval:A1", "dead-token", "", { to: "", subject: "", approved_by: "", approval_ref: "", context: "", detail: "" });
  r = await guardedSend(w.deps, msg());
  ok(r.reason === "duplicate" && r.prior === "delivery_unknown" && w.calls.length === 0, "a reservation that never got a result counts as may-have-left");

  // ---- a definite failure before DATA: send_failed, and a retry is allowed
  for (const [stage, error] of [["connect", "connect ECONNREFUSED"], ["auth", "SMTP 535: authentication failed"], ["rcpt", "SMTP 550: no such user"], ["mail_from", "SMTP 553: sender rejected"], ["data", "SMTP 554: not now"], ["config", "mailbox not configured"]] as const) {
    w = world(); w.script.push({ ok: false, error, stage });
    r = await guardedSend(w.deps, msg());
    const again = await guardedSend(w.deps, msg());
    ok(r.outcome === "send_failed" && r.error === error && again.outcome === "sent" && w.calls.length === 2, `a refusal at ${stage} is send_failed and the same key can be retried after the fix`);
  }
  w = world(); w.script.push({ ok: false, error: "x", stage: "auth" }, { ok: false, error: "SMTP timeout", stage: "body" });
  await guardedSend(w.deps, msg()); await guardedSend(w.deps, msg());
  ok((await guardedSend(w.deps, msg())).reason === "duplicate" && w.calls.length === 2, "a retry that then becomes unknown closes the key");

  // ---- owner approval reference (decideSend of lib/mandate.ts, conversation mode off)
  w = world();
  r = await guardedSend(w.deps, msg({ approval_ref: "" }));
  ok(r.outcome === "refused" && r.reason === "no_approval" && w.calls.length === 0 && w.keys.rows.length === 0, "a message without an approval reference is refused");
  ok((await guardedSend(w.deps, msg({ approved_by: "  " }))).reason === "no_approval" && w.calls.length === 0, "a message without an approver is refused");
  ok((await guardedSend(w.deps, msg({ text: "We will pay on signature and guarantee exclusivity." }))).outcome === "sent", "the owner's approval of this exact message is what releases it, whatever it says");
  ok((await guardedSend(w.deps, msg({ text: "  ", idempotency_key: "k3" }))).reason === "invalid" && w.calls.length === 1, "an empty message is refused by the policy");

  // ---- inputs and unreadable checks
  w = world();
  ok((await guardedSend(w.deps, msg({ to: "not an address" }))).reason === "invalid" && (await guardedSend(w.deps, msg({ idempotency_key: " " }))).reason === "invalid" && w.calls.length === 0, "no recipient address or no key: refused");
  w.listsDown = true;
  r = await guardedSend(w.deps, msg());
  ok(r.reason === "checks_unavailable" && w.calls.length === 0, "when the lists cannot be read nothing is sent (closed, not open)");
  w = world(); w.deps.keys = { ...w.deps.keys, reserve: async () => { throw new Error("append failed"); } };
  ok((await guardedSend(w.deps, msg())).reason === "checks_unavailable" && w.calls.length === 0, "when the reservation cannot be written nothing is sent");
  w = world(); w.deps.keys = { ...w.deps.keys, finish: async () => { throw new Error("append failed"); } };
  r = await guardedSend(w.deps, msg());
  ok(r.outcome === "sent" && (await guardedSend(w.deps, msg())).reason === "duplicate" && w.calls.length === 1, "a result row that could not be written still blocks a second send");

  // ---- helpers
  const k = contentKey("A@b.example", "s", "b", "2026-11-11");
  ok(k === contentKey(" a@B.example", "s", "b", "2026-11-11") && k !== contentKey("a@b.example", "s", "b", "2026-11-12") && k !== contentKey("a@b.example", "s2", "b", "2026-11-11") && k !== contentKey("c@b.example", "s", "b", "2026-11-11"), "the derived key is the recipient, subject, body and calendar day");
  ok(keyState([{ status: "reserved", token: "a" }, { status: "reserved", token: "b" }, { status: "sent", token: "b" }]).status === "reserved", "a result row from a call that did not own the reservation changes nothing");
  ok(keyState([{ status: "reserved", token: "a" }, { status: "send_failed", token: "a" }, { status: "reserved", token: "b" }]).owner === "b" && keyState([]).status === null, "after a definite failure the next reservation owns the key");
  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})();
