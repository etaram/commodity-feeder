import { NextRequest, NextResponse } from "next/server";
import { auditSession, gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { runNext } from "@/lib/missionrun";
import { liveRunDeps } from "@/lib/missionrun-live";
import { missionView } from "@/lib/missionview";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// POST /api/missions/ID/step: run exactly one step of one mission of the caller's workspace (lib/missionrun.ts) and
// return the mission. Analysts and admins; the audit session cannot call it (also refused by the middleware list in
// lib/auditscope.ts). One call, one step: no loop, no schedule. No model is called and nothing is sent; a step that
// would need either stops the mission with its question. The workspace comes from the session, never from the request.
export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  if (await auditSession()) return NextResponse.json({ ok: false, code: "forbidden", error: "The audit session cannot run a mission step" }, { status: 403 });
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const id = decodeURIComponent(String((await params).id || "")).slice(0, 80);
  if (!/^[A-Za-z0-9._:-]{3,80}$/.test(id)) return NextResponse.json({ ok: false, error: "mission id is required" }, { status: 400 });
  try {
    const r = await runNext(id, liveRunDeps(s.ws));
    if (!r.mission) return NextResponse.json({ ok: false, error: "mission not found" }, { status: 404 });
    await logActivity(s, "mission_step", id, `${r.ran || "no task"}: ${r.note}`.slice(0, 300)).catch(() => {});
    return NextResponse.json({ ok: r.ok, ran: r.ran, note: r.note, ...(r.error ? { error: r.error } : {}), mission: missionView(r.mission) }, { status: r.ok ? 200 : 500 });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
