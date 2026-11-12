import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { readDeal } from "@/lib/deal";
import { logActivity } from "@/lib/activity";
import { ownWorkspace } from "@/lib/scope";
import { dealGates, INQUIRY_LABEL, rfqReady } from "@/lib/dealgates";
import { submitDraft } from "@/lib/draftsend";
import { agentIo, ownerChat } from "@/lib/telegram";
import type { Readiness } from "@/lib/dealstate";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// POST {deal_id, draft_id}: "Submit for approval". The draft's current text becomes the deal agent's pending approval
// (Agent Approvals) and the owner gets the same Approve / Reject card in Telegram. Nothing is sent here: the owner's
// decision runs the existing path (lib/dealagent.ts decide -> lib/sendguard.ts). Submitting the same text twice
// returns the same approval. Drafts go out from the owner's mailbox, so only the original workspace submits.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  if (!ownWorkspace(s.ws)) return NextResponse.json({ ok: false, error: "Submitting for the owner's approval is limited to the owner's workspace" }, { status: 403 });
  const b = await req.json().catch(() => ({}));
  const dealId = String(b.deal_id || "").slice(0, 120), draftId = String(b.draft_id || "").slice(0, 60);
  if (!dealId || !draftId) return NextResponse.json({ ok: false, error: "deal_id and draft_id are required" }, { status: 400 });
  try {
    const d = await readDeal(dealId, s.ws);
    const g = (await dealGates(dealId, d.records).catch(() => ({}))) as { readiness?: Readiness };
    const owner = await ownerChat().catch(() => null);
    const r = await submitDraft(agentIo, { dealId, draftId, ws: s.ws, by: s.email, chat: owner?.chat_id || "", lang: owner?.lang || "he",
      kindLabel: rfqReady(g.readiness) ? "request for quotation" : INQUIRY_LABEL });
    if (!r.ok) return NextResponse.json({ ok: false, code: r.code, error: r.error }, { status: r.status });
    await logActivity(s, r.duplicate ? "deal_draft_submit_duplicate" : "deal_draft_submit", dealId, `${draftId} rev${r.rev} ${r.approval_id} ${r.state}`);
    return NextResponse.json(r);
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
