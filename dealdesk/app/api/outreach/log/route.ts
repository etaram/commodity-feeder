import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logRows } from "@/lib/outreach/outbox";
import { fail, q } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";

export const dynamic = "force-dynamic";

// GET ?campaign_id=&account_id=&limit=200  -> { ok, events: [{time, campaign_id, kind, by, data}] } newest first
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    const snap = await routeDeps().store.load();
    const limit = Math.max(1, Math.min(1000, Number(q(req, "limit")) || 200));
    const rows = logRows(snap, s.ws, { campaign_id: q(req, "campaign_id") || undefined, account_id: q(req, "account_id") || undefined }).slice(0, limit);
    return NextResponse.json({ ok: true, events: rows.map((r) => ({ time: r.time, campaign_id: r.campaign_id, kind: r.status, by: r.by, data: r.data })) });
  } catch (e) { return fail(e); }
}
