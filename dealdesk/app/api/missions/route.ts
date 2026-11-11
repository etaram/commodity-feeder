import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { createMission, MISSION_TYPES, type Mission, type MissionType } from "@/lib/mission";
import { sheetsMissionStore } from "@/lib/missionstore-sheets";

export const dynamic = "force-dynamic";

// Missions of the caller's workspace (lib/mission.ts on the "Missions" tab). This step records a mission and lists
// missions; it adds no task, runs no task and calls no model. Analysts and admins only. The workspace and the
// represented organisation come from the session, never from the request.
const MAX_BUDGET_USD = 1000; // ceiling for one mission in this release; nothing spends it yet
const summary = (m: Mission) => ({ id: m.id, type: m.type, goal: m.goal, deal_id: m.deal_id, status: m.status, cost_budget_usd: m.cost_budget_usd, spent_usd: m.spent_usd,
  next_decision: m.next_decision, tasks: m.tasks.length, created_at: m.created_at, updated_at: m.updated_at });

// GET [?deal_id=DEAL]: the workspace's missions, newest first.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const dealId = String(req.nextUrl.searchParams.get("deal_id") || "").slice(0, 120);
  try {
    const all = await sheetsMissionStore().list(s.ws);
    return NextResponse.json({ ok: true, missions: all.filter((m) => !dealId || m.deal_id === dealId).map(summary) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}

// POST {type, goal, deal_id?, cost_budget_usd}: record one mission. The same request returns the same mission.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const type = String(b.type || "") as MissionType, goal = String(b.goal || "").replace(/\s+/g, " ").trim().slice(0, 500);
  const dealId = String(b.deal_id || "").trim().slice(0, 120), budget = b.cost_budget_usd;
  if (!MISSION_TYPES.includes(type)) return NextResponse.json({ ok: false, error: `type is one of: ${MISSION_TYPES.join(", ")}` }, { status: 400 });
  if (!goal) return NextResponse.json({ ok: false, error: "goal is required" }, { status: 400 });
  if (typeof budget !== "number" || !Number.isFinite(budget) || budget < 0) return NextResponse.json({ ok: false, error: "cost budget is a number in USD, 0 or more" }, { status: 400 });
  if (budget > MAX_BUDGET_USD) return NextResponse.json({ ok: false, error: `cost budget cannot exceed ${MAX_BUDGET_USD} USD` }, { status: 400 });
  try {
    const r = await createMission({ store: sheetsMissionStore(), now: () => Date.now() },
      { workspace: s.ws, type, goal, represented_org: s.ws, deal_id: dealId, cost_budget_usd: budget, allowed_tools: [], stop_rules: [] });
    if (!r.ok) return NextResponse.json({ ok: false, error: r.error }, { status: 400 });
    if (r.created) await logActivity(s, "mission_create", r.mission.id, `${type} ${dealId}`.trim()).catch(() => {});
    return NextResponse.json({ ok: true, created: r.created, mission: summary(r.mission) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
