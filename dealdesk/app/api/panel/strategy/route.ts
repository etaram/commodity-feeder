import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { cleanStrategy, getStrategy, saveStrategy } from "@/lib/strategy";
import { ownWorkspace } from "@/lib/scope";
import { logActivity } from "@/lib/activity";

// GET: this workspace's strategy. POST {partners:[ISO3], focus:[words], excluded:[ISO3]} (admin): replaces it.
// The original workspace's strategy lives in the pipeline (leads/dealfit.py), not here.
export const dynamic = "force-dynamic";
export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  if (ownWorkspace(s.ws)) return NextResponse.json({ ok: true, ws: s.ws, owner: true, strategy: null });
  return NextResponse.json({ ok: true, ws: s.ws, owner: false, strategy: (await getStrategy(s.ws)) || cleanStrategy() });
}
export async function POST(req: NextRequest) {
  const { s, res } = await gate("admin");
  if (!s) return res;
  if (ownWorkspace(s.ws)) return NextResponse.json({ ok: false, error: "the original workspace's strategy is set in the pipeline" }, { status: 400 });
  const st = cleanStrategy(await req.json().catch(() => ({})));
  await saveStrategy(s.ws, st, s.email);
  await logActivity(s, "strategy_update", `partners ${st.partners.join(",")} | focus ${st.focus.join(",")} | excluded ${st.excluded.join(",")}`.slice(0, 300));
  return NextResponse.json({ ok: true, strategy: st });
}
