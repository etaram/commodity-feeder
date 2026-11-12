import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { outboxItems, reconcileDelivery } from "@/lib/outreach/outbox";
import { bad, body, fail, q } from "@/lib/outreach/http";
import { logActivity } from "@/lib/activity";
import { routeDeps } from "@/lib/outreach";
import { APPROVER_REFUSAL, mayApprove } from "@/lib/approver";

export const dynamic = "force-dynamic";

// GET ?campaign_id=&status=queued|sending|sent|cancelled|failed|needs_review|delivery_unknown  -> { ok, items, counts }
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    const snap = await routeDeps().store.load();
    const all = outboxItems(snap, s.ws, q(req, "campaign_id") || undefined);
    const status = q(req, "status");
    const counts: Record<string, number> = {};
    for (const x of all) counts[x.status] = (counts[x.status] || 0) + 1;
    return NextResponse.json({ ok: true, items: (status ? all.filter((x) => x.status === status) : all).slice(0, 500), counts });
  } catch (e) { return fail(e); }
}

// POST { action: "reconcile", id, decision?: "sent" | "not_sent" }  (admin)
// Moves a delivery_unknown / needs_review item on. Without a decision the provider is asked; with one, the owner has
// checked and decides. Admin only, because not_sent puts the item back in the queue, which can lead to a send.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("admin");
  if (!s) return res;
  const ap = await mayApprove(s.email);
  if (!ap.ok) return NextResponse.json({ ok: false, code: "not_approver", error: APPROVER_REFUSAL }, { status: 403 });
  try {
    const b = await body(req);
    if (b.action !== "reconcile") return bad("unknown action");
    const id = String(b.id || "").slice(0, 80);
    if (!id) return bad("id is required");
    if (b.decision !== undefined && b.decision !== "sent" && b.decision !== "not_sent") return bad("decision must be sent or not_sent");
    const r = await reconcileDelivery(routeDeps(), s.ws, id, s.email, b.decision);
    if (!r.ok) return bad(r.error, /not found/.test(r.error) ? 404 : 400);
    await logActivity(s, "outreach_reconcile", id, `${r.outcome} (${r.source})`);
    return NextResponse.json(r);
  } catch (e) { return fail(e); }
}
