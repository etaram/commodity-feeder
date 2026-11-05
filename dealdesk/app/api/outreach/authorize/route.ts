import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { authorizeCampaign } from "@/lib/outreach/campaign";
import { bad, body, fail } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";

export const dynamic = "force-dynamic";

// POST { campaign_id, confirm_scope_hash }  admin only. confirm_scope_hash is the scope.scope_hash the admin reviewed
// (GET /api/outreach/campaign?id=...); it must equal the current scope, so what is authorized is exactly what was seen.
// Records who, when, the scope hash, the plan hash and the audience. Response { ok, authorization } or { ok:false, errors }.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("admin");
  if (!s) return res;
  try {
    const b = await body(req);
    const cid = String(b.campaign_id || "");
    if (!cid) return bad("campaign_id is required");
    const d = routeDeps();
    const r = await authorizeCampaign(d, d.transport, s.ws, cid, String(b.confirm_scope_hash || ""), s.email);
    if (!r.ok) return NextResponse.json({ ok: false, errors: r.errors }, { status: 400 });
    await logActivity(s, "outreach_authorize", cid, `scope ${r.authorization.scope_hash.slice(0, 12)}, ${r.authorization.audience.length} accounts`);
    return NextResponse.json({ ok: true, authorization: r.authorization });
  } catch (e) { return fail(e); }
}
