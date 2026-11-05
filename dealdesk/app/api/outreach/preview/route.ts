import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { previewMessage } from "@/lib/outreach/outbox";
import { bad, body, fail } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// POST { campaign_id, account_id, step?: 0, adapt?: false }
// -> { ok, to, from, subject, body, attachments, claims_used: [{id,text,source}], checks: [{name,ok,detail}],
//      adapted: {subject,body}|null, adapt_rejected: string[], scope_hash, needs_reauthorization }
// adapt=true makes at most one bounded model call; its output is validated in code and rejected if it adds anything.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try {
    const b = await body(req);
    if (!b.campaign_id || !b.account_id) return bad("campaign_id and account_id are required");
    const step = Math.max(0, Math.min(5, Number(b.step) || 0));
    const p = await previewMessage(routeDeps(), s.ws, String(b.campaign_id), String(b.account_id), step, b.adapt === true);
    return NextResponse.json({ ...p, ok: true, sendable: p.ok });
  } catch (e) { return fail(e); }
}
