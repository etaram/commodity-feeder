// A deal draft approved by the owner with AGENT_MAIL_LIVE=0 (tests/mailoff.test.ts pattern, with the REAL mailer):
// the whole path (submit -> decide -> guardedSend -> lib/mailer.ts) opens no connection and the refusal is recorded on
// the approval and on the draft. Any socket opened during the test is a failure.
import net from "net";
import tls from "tls";
import { TABS } from "./mocks/sheets-isolation";
import { mailReady } from "@/lib/mailer";
import { readDeal } from "@/lib/deal";
import { saveDraftEdit, submitDraft } from "@/lib/draftsend";
import { decide, type Io } from "@/lib/dealagent";
import { guardedSend, sheetsGuardDeps } from "@/lib/sendguard";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
(async () => {
  let opened = 0;
  const n0 = net.connect, t0 = tls.connect;
  (net as { connect: unknown }).connect = (...a: unknown[]) => { opened++; return (n0 as (...x: unknown[]) => unknown)(...a); };
  (tls as { connect: unknown }).connect = (...a: unknown[]) => { opened++; return (t0 as (...x: unknown[]) => unknown)(...a); };
  process.env.ZOHO_SMTP_USER = "desk@example.test"; process.env.ZOHO_SMTP_PASS = "not-a-real-password";
  process.env.AGENT_MAIL_LIVE = "0";
  delete process.env.SEND_APPROVERS;
  TABS["Users"] = [["owner@sinder.test", "owner@sinder.test", "admin", "active", "", "password", "", "", "", "", "", "", ""]];
  ok(mailReady() === false, "AGENT_MAIL_LIVE=0: the mailbox is not ready although its credentials are set");
  const io: Io = { send: async () => {}, kick: async () => {}, approver: async () => true };
  const a = await saveDraftEdit({ dealId: "TED-OFF", ws: "sinder", by: "a@sinder.test", data: { to_name: "S", to_email: "sales@supplier.example", subject: "Capability inquiry", body: "Dear team ..." } });
  const s = await submitDraft(io, { dealId: "TED-OFF", draftId: a.ok ? a.record_id : "", ws: "sinder", by: "a@sinder.test", chat: "C", lang: "en", kindLabel: "capability inquiry (qualification), not an RFQ" });
  const id = s.ok ? s.approval_id : "";
  await decide(io, "C", id, true, false, "owner@sinder.test");
  const st = (TABS["Agent Approvals"] || []).filter((r) => r[0] === id).map((r) => String(r[4]));
  const d = (await readDeal("TED-OFF", "sinder")).records.find((x) => x.kind === "draft")!;
  ok(st.slice(-1)[0] === "send_failed" && d.status === "refused" && d.data.sent === false, "approved with mail off: the approval is send_failed and the draft refused, never sent");
  // the guard's own live dependencies with the real sendMail: it returns at the config stage
  const g = await guardedSend(sheetsGuardDeps(), { workspace: "sinder", to: "sales@supplier.example", subject: "x", text: "y", idempotency_key: "draftmailoff:1", approved_by: "owner@sinder.test", approval_ref: "Agent Approvals:X", context: "test" });
  ok(g.outcome === "send_failed" && g.stage === "config", "the real mailer behind the guard refuses at the config stage");
  ok(opened === 0, "no network connection was opened");
  process.exit(fail ? 1 : 0);
})();
