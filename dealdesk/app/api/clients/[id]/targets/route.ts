import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { loadDossier, saveDossier } from "@/lib/dossier";
import { discoverProspects, draftProfiles, explainFit, loadData, storeProspects, validateProfiles, type Profile } from "@/lib/targeting";

export const dynamic = "force-dynamic";
export const maxDuration = 120;
type Ctx = { params: Promise<{ id: string }> };

// POST /api/clients/:id/targets {action?: "profiles"|"discover"|"both" (default both), explain?: boolean, profiles?: Profile[] (edited)}
// profiles: drafted from the dossier only (needs status reviewed or active); stored in the dossier (new version, status kept).
// discover: prospects from tenders, awards and the supplier universe (needs status active); stored in 'Prospects'.
// -> {ok, profiles, rejected, prospects: {total, by_stage, stored, excluded, competitors_skipped}, explained}
export async function POST(req: NextRequest, { params }: Ctx) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const { id } = await params;
  const b = await req.json().catch(() => ({}));
  const action = ["profiles", "discover", "both"].includes(b.action) ? b.action : "both";
  try {
    const cur = await loadDossier(s.ws, id);
    if (!cur) return NextResponse.json({ ok: false, error: "client not found" }, { status: 404 });
    const d = cur.dossier;
    let profiles = (Array.isArray(d.targets) ? d.targets : []) as Profile[], rejected: { item: unknown; reason: string }[] = [], version = cur.version;
    if (action !== "discover") {
      if (d.status === "draft") return NextResponse.json({ ok: false, error: "review the dossier before targeting (status is draft)" }, { status: 409 });
      // edited profiles from the screen are validated the same way as the model's (grounded in claim ids)
      const r = Array.isArray(b.profiles) ? validateProfiles({ profiles: b.profiles }, d) : await draftProfiles(d);
      profiles = r.profiles; rejected = r.rejected;
      if (profiles.length) {
        const keep = d.status;
        d.targets = profiles; d.targets_at = new Date().toISOString().slice(0, 19) + "Z"; d.status = keep;
        version = await saveDossier(s.ws, d, cur.version + 1, s.email);
      }
    }
    let prospects = null, explained = 0;
    if (action !== "profiles") {
      if (d.status !== "active") return NextResponse.json({ ok: action === "both", profiles, rejected, version, error: "prospect discovery runs on an active dossier only" }, { status: action === "both" ? 200 : 409 });
      if (!profiles.length) return NextResponse.json({ ok: false, error: "no target profiles yet" }, { status: 409 });
      const found = discoverProspects(s.ws, d, profiles, await loadData(profiles));
      if (b.explain === true) explained = await explainFit(d, found.prospects).catch(() => 0);
      const stored = await storeProspects(s.ws, id, found.prospects);
      const by_stage = found.prospects.reduce((m, p) => ({ ...m, [p.stage]: (m[p.stage] || 0) + 1 }), {} as Record<string, number>);
      prospects = { total: found.prospects.length, by_stage, stored, excluded: found.excluded, competitors_skipped: found.competitors_skipped };
    }
    await logActivity(s, "client_targets", id, `${action}: ${profiles.length} profiles${prospects ? `, ${prospects.total} prospects` : ""}`);
    return NextResponse.json({ ok: true, version, profiles, rejected, prospects, explained });
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}
