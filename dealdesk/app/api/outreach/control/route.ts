import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { hasRole } from "@/lib/auth";
import { cancelCampaign, clearEmergencyStop, emergencyStop, pauseCampaign, startCampaign, withdrawAuthorization } from "@/lib/outreach/outbox";
import { bad, body, fail } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";

export const dynamic = "force-dynamic";

// POST { action, campaign_id?, reason? }
//   analyst: pause | cancel | withdraw (authorization withdrawal, campaign stopped) | emergency_stop (whole workspace)
//   admin:   start | resume | clear_emergency_stop
// Stopping is open to analysts on purpose; anything that can lead to sending needs an admin.
const ADMIN = new Set(["start", "resume", "clear_emergency_stop"]);
const ALL = new Set(["pause", "cancel", "withdraw", "emergency_stop", ...ADMIN]);

export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try {
    const b = await body(req);
    const action = String(b.action || "");
    if (!ALL.has(action)) return bad("unknown action");
    if (ADMIN.has(action) && !hasRole(s, "admin")) return NextResponse.json({ ok: false, code: "forbidden", error: "This needs the admin role" }, { status: 403 });
    const d = routeDeps();
    const reason = String(b.reason || "").slice(0, 300);
    if (action === "emergency_stop") {
      const r = await emergencyStop(d, s.ws, s.email, reason || "emergency stop");
      await logActivity(s, "outreach_emergency_stop", s.ws, `${r.paused} campaigns paused`);
      return NextResponse.json({ ok: true, ...r });
    }
    if (action === "clear_emergency_stop") {
      await clearEmergencyStop(d, s.ws, s.email);
      await logActivity(s, "outreach_emergency_clear", s.ws, "");
      return NextResponse.json({ ok: true });
    }
    const cid = String(b.campaign_id || "");
    if (!cid) return bad("campaign_id is required");
    const r = action === "pause" ? await pauseCampaign(d, s.ws, cid, s.email, reason || "paused")
      : action === "cancel" ? await cancelCampaign(d, s.ws, cid, s.email, reason || "cancelled")
      : action === "withdraw" ? await withdrawAuthorization(d, s.ws, cid, s.email, reason || "authorization withdrawn")
      : await startCampaign(d, s.ws, cid, s.email);
    if (!r.ok) return bad(r.error);
    await logActivity(s, `outreach_${action}`, cid, reason);
    return NextResponse.json(r);
  } catch (e) { return fail(e); }
}
