import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { mailReady, sendMail } from "@/lib/mailer";
import { appendRow } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";

// Send one composed message from the panel, from the connected mailbox. The person pressed Send and then confirmed,
// with the recipients, subject and body on screen: that press is the approval. Each recipient gets a separate
// message; every send is written to the 'Outbox' tab. A daily cap guards against a runaway loop.
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const DAILY = Number(process.env.PANEL_MAIL_DAILY || 40);
let day = "", used = 0;

export async function POST(req: NextRequest) {
  const auth = await gate("analyst");
  if (!auth.s) return auth.res;
  if (!mailReady()) return NextResponse.json({ ok: false, error: "No mailbox is connected" }, { status: 503 });
  const b = await req.json().catch(() => ({}));
  const to = (Array.isArray(b.to) ? b.to : String(b.to || "").split(/[,;\s]+/)).map((x: unknown) => String(x).trim()).filter((x: string) => /@/.test(x)).slice(0, 5);
  const subject = String(b.subject || "").slice(0, 200), body = String(b.body || "").slice(0, 20000), ctx = String(b.context || "").slice(0, 200);
  if (!to.length || !subject.trim() || !body.trim()) return NextResponse.json({ ok: false, error: "recipient, subject and body are required" }, { status: 400 });
  const today = new Date().toISOString().slice(0, 10);
  if (today !== day) { day = today; used = 0; }
  if (used + to.length > DAILY) return NextResponse.json({ ok: false, error: `Daily sending limit (${DAILY}) reached` }, { status: 429 });
  used += to.length;
  const results = [];
  for (const addr of to) {
    const r = await sendMail({ to: addr, subject, text: body });
    results.push({ to: addr, ok: r.ok, error: r.error || "" });
    await appendRow("Outbox", [new Date().toISOString(), auth.s.email, addr, subject, r.ok ? "sent" : "failed", r.id || "", r.error || "", ctx]).catch(() => {});
  }
  await logActivity(auth.s, "mail_send", ctx || subject.slice(0, 80), results.map((x) => `${x.to}:${x.ok ? "sent" : "failed"}`).join(" "));
  return NextResponse.json({ ok: results.every((x) => x.ok), results, from: process.env.ZOHO_SMTP_USER });
}
