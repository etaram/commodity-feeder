import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { loadDossier } from "@/lib/dossier";
import { readProspects } from "@/lib/targeting";

export const dynamic = "force-dynamic";
type Ctx = { params: Promise<{ id: string }> };

// GET /api/clients/:id/prospects?stage=active_signal|evidenced_need|structural_fit&profile=TP-...
// -> {ok, prospects: Prospect[], by_stage}. Only this workspace's rows for this client.
export async function GET(req: NextRequest, { params }: Ctx) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const { id } = await params;
  try {
    if (!(await loadDossier(s.ws, id))) return NextResponse.json({ ok: false, error: "client not found" }, { status: 404 });
    const stage = req.nextUrl.searchParams.get("stage") || "", profile = req.nextUrl.searchParams.get("profile") || "";
    const all = await readProspects(s.ws, id);
    const by_stage = all.reduce((m, p) => ({ ...m, [p.stage]: (m[p.stage] || 0) + 1 }), {} as Record<string, number>);
    const prospects = all.filter((p) => (!stage || p.stage === stage) && (!profile || p.profile_id === profile));
    return NextResponse.json({ ok: true, prospects, by_stage });
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}
