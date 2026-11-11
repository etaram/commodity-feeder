import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { mailReady } from "@/lib/mailer";
import { contentKey, guardedSend, sheetsGuardDeps } from "@/lib/sendguard";
import { sha } from "@/lib/outreach/store";
import { appendRow } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";

// Send one composed message from the panel, from the connected mailbox. The person pressed Send and then confirmed,
// with the recipients, subject and body on screen: that press is the approval. Each recipient gets a separate
// message; every send is written to the 'Outbox' tab. A daily cap guards against a runaway loop.
// Every message goes through lib/sendguard.ts: emergency stop, opt-out list, and an idempotency key per recipient, so
// a double click, a browser retry or a resend after a timeout cannot deliver the same message twice. The key comes
// from the client's request_id; without one it is the hash of recipient + subject + body + the calendar day, which
// means the identical message to the same person goes out once a day.
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const DAILY = Number(process.env.PANEL_MAIL_DAILY || 40);
let day = "", used = 0;

export async function POST(req: NextRequest) {
  // The mailbox is the owner's own: only an admin of the original workspace sends from it, and the click is the
  // approval (recorded in the Outbox tab and the activity log below). Analysts and other workspaces cannot send.
  const auth = await gate("admin");
  if (!auth.s) return auth.res;
  if (auth.s.ws && auth.s.ws !== "sinder") return NextResponse.json({ ok: false, error: "Sending from this mailbox is limited to the owner" }, { status: 403 });
  if (!mailReady()) return NextResponse.json({ ok: false, error: "No mailbox is connected" }, { status: 503 });
  const b = await req.json().catch(() => ({}));
  const to = (Array.isArray(b.to) ? b.to : String(b.to || "").split(/[,;\s]+/)).map((x: unknown) => String(x).trim()).filter((x: string) => /@/.test(x)).slice(0, 5);
  const subject = String(b.subject || "").slice(0, 200), body = String(b.body || "").slice(0, 20000), ctx = String(b.context || "").slice(0, 200);
  if (!to.length || !subject.trim() || !body.trim()) return NextResponse.json({ ok: false, error: "recipient, subject and body are required" }, { status: 400 });
  const today = new Date().toISOString().slice(0, 10);
  if (today !== day) { day = today; used = 0; }
  if (used + to.length > DAILY) return NextResponse.json({ ok: false, error: `Daily sending limit (${DAILY}) reached` }, { status: 429 });
  used += to.length;
  const requestId = String(b.request_id || "").trim().slice(0, 120);
  const results = [];
  for (const addr of to) {
    const key = requestId ? `panel:${sha(`${requestId}\n${addr.toLowerCase()}`)}` : contentKey(addr, subject, body, today);
    const r = await guardedSend(sheetsGuardDeps(), { workspace: auth.s.ws || "sinder", to: addr, subject, text: body, idempotency_key: key, approved_by: auth.s.email, approval_ref: `panel-send:${requestId || key}`, context: ctx || "panel" });
    // sent | send_failed (nothing left, safe to retry) | delivery_unknown (may have left: check Sent first) | stopped | duplicate
    const status = r.outcome === "refused" ? (r.reason === "duplicate" ? "duplicate" : "stopped") : r.outcome;
    const error = r.outcome === "sent" ? "" : r.outcome === "delivery_unknown" ? "It is not known whether this message was sent. Check the Sent folder before sending it again or by hand."
      : r.reason === "duplicate" ? (r.prior === "sent" ? "This exact message was already sent to this recipient. It was not sent again." : "An earlier send of this exact message may have left. Check the Sent folder; it was not sent again.")
      : r.outcome === "refused" ? r.message : `Not sent, nothing left the system (${r.error}). Safe to try again.`;
    results.push({ to: addr, ok: r.outcome === "sent", status, error });
    await appendRow("Outbox", [new Date().toISOString(), auth.s.email, addr, subject, status === "send_failed" ? "failed" : status, r.id, r.error || (r.outcome === "sent" ? "" : r.message), ctx]).catch(() => {});
  }
  await logActivity(auth.s, "mail_send", ctx || subject.slice(0, 80), results.map((x) => `${x.to}:${x.status}`).join(" "));
  return NextResponse.json({ ok: results.every((x) => x.ok), results, from: process.env.ZOHO_SMTP_USER });
}
