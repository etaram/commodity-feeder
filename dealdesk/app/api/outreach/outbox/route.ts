import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { outboxItems } from "@/lib/outreach/outbox";
import { fail, q } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";

export const dynamic = "force-dynamic";

// GET ?campaign_id=&status=queued|sending|sent|cancelled|failed|needs_review  -> { ok, items, counts }
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
