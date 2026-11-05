import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { moveStage, readAccounts, upsertAccounts } from "@/lib/outreach/campaign";
import { contactHistory } from "@/lib/outreach/linkedin-tasks";
import { bad, body, fail, q } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";
import type { AccountStage } from "@/lib/outreach/types";

export const dynamic = "force-dynamic";

// GET ?campaign_id=...                 the campaign's reviewed account list
// GET ?campaign_id=...&account_id=...  one account with its cross-channel contact history
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    const cid = q(req, "campaign_id"), aid = q(req, "account_id");
    if (!cid) return bad("campaign_id is required");
    const snap = await routeDeps().store.load();
    const accounts = readAccounts(snap, s.ws, cid);
    if (aid) {
      const a = accounts.find((x) => x.id === aid);
      if (!a) return NextResponse.json({ ok: false, error: "account not found" }, { status: 404 });
      return NextResponse.json({ ok: true, account: a, history: contactHistory(snap, s.ws, aid) });
    }
    return NextResponse.json({ ok: true, accounts });
  } catch (e) { return fail(e); }
}

// POST { campaign_id, accounts: [{company, contact_name, first_name, email, linkedin_url, country, contact_source, fields, notes}] }
//   adds or updates accounts (new ones start at "identified")
// POST { campaign_id, account_id, stage, reason }  moves one account one stage (requirements checked in code)
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try {
    const b = await body(req);
    const cid = String(b.campaign_id || "");
    if (!cid) return bad("campaign_id is required");
    const d = routeDeps();
    if (Array.isArray(b.accounts)) {
      const r = await upsertAccounts(d, s.ws, cid, b.accounts, s.email);
      await logActivity(s, "outreach_accounts", cid, `added ${r.added}, updated ${r.updated}`);
      return NextResponse.json({ ok: true, ...r });
    }
    if (b.account_id && b.stage) {
      const a = await moveStage(d, s.ws, cid, String(b.account_id), String(b.stage) as AccountStage, String(b.reason || ""), s.email);
      await logActivity(s, "outreach_stage", `${cid} ${a.id}`, a.stage);
      return NextResponse.json({ ok: true, account: a });
    }
    return bad("send accounts[] or account_id with stage");
  } catch (e) { return fail(e); }
}
