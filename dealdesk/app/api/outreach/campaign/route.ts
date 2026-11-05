import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { killSwitch, listCampaigns, needsReauthorization, readAccounts, readCampaign, saveCampaign, scopeSummary } from "@/lib/outreach/campaign";
import { body, fail, q } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";

export const dynamic = "force-dynamic";

// GET ?id=CMP-...  one campaign with its accounts and the scope an admin would authorize.
// GET              all campaigns of the workspace (summary) and the emergency-stop state.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    const d = routeDeps();
    const snap = await d.store.load();
    const id = q(req, "id");
    if (id) {
      const c = readCampaign(snap, s.ws, id);
      if (!c) return NextResponse.json({ ok: false, error: "campaign not found" }, { status: 404 });
      return NextResponse.json({ ok: true, campaign: c, accounts: readAccounts(snap, s.ws, id), scope: scopeSummary(snap, s.ws, c), kill_switch: killSwitch(snap, s.ws) });
    }
    const all = listCampaigns(snap, s.ws).map((c) => ({
      id: c.id, name: c.plan.name, client: c.plan.client, segment: c.plan.segment, channel: c.plan.channel, status: c.status, status_reason: c.status_reason,
      needs_reauthorization: c.status !== "draft" && needsReauthorization(c), accounts: readAccounts(snap, s.ws, c.id).length, updated_at: c.updated_at,
    }));
    return NextResponse.json({ ok: true, campaigns: all, kill_switch: killSwitch(snap, s.ws) });
  } catch (e) { return fail(e); }
}

// POST { id?, plan }  create (no id) or update a campaign plan. A material change to an authorized campaign
// blocks sending until it is re-authorized (needs_reauthorization: true in the response).
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try {
    const b = await body(req);
    const d = routeDeps();
    const r = await saveCampaign(d, s.ws, { id: b.id ? String(b.id) : undefined, plan: b.plan }, s.email);
    await logActivity(s, "outreach_campaign_save", r.campaign.id, `${r.campaign.plan.name} ${r.campaign.status}${r.needs_reauthorization ? " needs re-authorization" : ""}`);
    return NextResponse.json({ ok: true, campaign: r.campaign, errors: r.errors, needs_reauthorization: r.needs_reauthorization });
  } catch (e) { return fail(e); }
}
