import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { handleReply } from "@/lib/outreach/outbox";
import { bad, body, fail } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";
import type { ReplyCategory } from "@/lib/outreach/types";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

const CATS: ReplyCategory[] = ["opt_out", "hard_bounce", "soft_bounce", "out_of_office", "interested", "meeting_booked", "question", "referral", "not_interested", "needs_human"];

// POST { campaign_id, account_id, text, subject?, category? }  records a reply (pasted by a person, or later from an
// inbox hook). Without category it is classified: rules first (opt-out, bounce codes, out-of-office), a bounded
// model call for the rest. -> { ok, category, classified_by, effect: {stop, suppress, stage, human}, cancelled }
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try {
    const b = await body(req);
    if (!b.campaign_id || !b.account_id) return bad("campaign_id and account_id are required");
    const category = CATS.includes(b.category) ? (b.category as ReplyCategory) : undefined;
    const r = await handleReply(routeDeps(), s.ws, { campaign_id: String(b.campaign_id), account_id: String(b.account_id), text: String(b.text || "").slice(0, 20000), subject: String(b.subject || "").slice(0, 300), category }, s.email);
    await logActivity(s, "outreach_reply", `${b.campaign_id} ${b.account_id}`, r.category);
    return NextResponse.json({ ok: true, ...r });
  } catch (e) { return fail(e); }
}
