import { NextRequest, NextResponse } from "next/server";
import { auditSession, gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { REASONS, type Reason } from "@/lib/outcomes";
import { logFeedback } from "@/lib/outcomelog";

export const dynamic = "force-dynamic";

// POST {deal_id, reason}: one feedback reason on a deal, from the fixed list in lib/outcomes.ts, stored as a ledger
// event of type "feedback" on the tab "Outcomes". Analysts and admins (the owner); the audit session cannot write.
// The workspace and the actor come from the session, never from the request. Feedback is a label: it changes no
// deal record, no route state and no ranking, and nothing is trained on it.
export async function POST(req: NextRequest) {
  if (await auditSession()) return NextResponse.json({ ok: false, code: "forbidden", error: "The audit session cannot write" }, { status: 403 });
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const dealId = String(b.deal_id || "").trim().slice(0, 120), reason = String(b.reason || "") as Reason;
  if (!dealId) return NextResponse.json({ ok: false, error: "deal_id is required" }, { status: 400 });
  if (!REASONS.includes(reason)) return NextResponse.json({ ok: false, error: `reason is one of: ${REASONS.join(", ")}` }, { status: 400 });
  const stored = await logFeedback({ workspace: s.ws, deal_id: dealId, at: new Date().toISOString(), actor: s.email, reason });
  // logFeedback never throws; false means the ledger could not be written (it is logged) and the caller is told so
  if (!stored) return NextResponse.json({ ok: false, error: "The feedback could not be saved. Try again." }, { status: 503 });
  await logActivity(s, "deal_feedback", dealId, reason).catch(() => {});
  return NextResponse.json({ ok: true, deal_id: dealId, reason });
}
