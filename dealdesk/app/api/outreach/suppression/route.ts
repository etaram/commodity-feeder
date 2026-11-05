import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { hasRole } from "@/lib/auth";
import { addSuppression, suppressionEntries } from "@/lib/outreach/suppression";
import { cancelQueued } from "@/lib/outreach/campaign";
import { bad, body, fail } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";

export const dynamic = "force-dynamic";

// GET -> { ok, entries: [{value, campaign_id, reason, source, status, at, by}] }
export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    return NextResponse.json({ ok: true, entries: suppressionEntries(await routeDeps().store.load(), s.ws) });
  } catch (e) { return fail(e); }
}

// POST { value: "name@x.com" | "@x.com", reason, campaign_id?: "*" }  adds an entry and cancels matching queued items.
// POST { value, remove: true, reason }  admin only: lifts an entry (kept in the history).
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try {
    const b = await body(req);
    const remove = b.remove === true;
    if (remove && !hasRole(s, "admin")) return NextResponse.json({ ok: false, code: "forbidden", error: "This needs the admin role" }, { status: 403 });
    if (!b.value) return bad("value is required");
    const d = routeDeps();
    const cid = String(b.campaign_id || "*");
    const e = await addSuppression(d, s.ws, String(b.value), String(b.reason || (remove ? "lifted" : "manual")), "manual", s.email, cid, remove ? "removed" : "active");
    let cancelled = 0;
    if (!remove) {
      const snap = await d.store.load();
      cancelled = await cancelQueued(d, snap, s.ws, (x) => {
        const to = String(x.to || "").toLowerCase();
        return (cid === "*" || x.campaign_id === cid) && (to === e.value || (e.value.startsWith("@") && to.endsWith(e.value)));
      }, "suppressed", s.email);
    }
    await logActivity(s, remove ? "outreach_unsuppress" : "outreach_suppress", e.value, e.reason);
    return NextResponse.json({ ok: true, entry: e, cancelled });
  } catch (e) { return fail(e); }
}
