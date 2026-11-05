import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { applyPatch, loadDossier, outreachClaims, prioritizeQuestions, saveDossier, type Patch } from "@/lib/dossier";

export const dynamic = "force-dynamic";
type Ctx = { params: Promise<{ id: string }> };
const notFound = () => NextResponse.json({ ok: false, error: "client not found" }, { status: 404 });

// GET /api/clients/:id -> {ok, version, dossier, questions (prioritised), outreach_claims}
// A client id of another workspace returns 404 (rows are read by workspace and client id).
export async function GET(_req: NextRequest, { params }: Ctx) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const { id } = await params;
  try {
    const cur = await loadDossier(s.ws, id);
    if (!cur) return notFound();
    return NextResponse.json({ ok: true, version: cur.version, dossier: cur.dossier, questions: prioritizeQuestions(cur.dossier), outreach_claims: outreachClaims(cur.dossier).map((c) => c.id) });
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}

// PUT /api/clients/:id {version, ...Patch} (see lib/dossier.ts Patch): edit fields and claims, approve, verify,
// resolve contradictions, answer questions, change status (draft -> reviewed -> active). 409 when version is stale.
export async function PUT(req: NextRequest, { params }: Ctx) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const { id } = await params;
  const b = (await req.json().catch(() => ({}))) as Patch & { version?: number };
  try {
    const cur = await loadDossier(s.ws, id);
    if (!cur) return notFound();
    if (b.version !== undefined && Number(b.version) !== cur.version) return NextResponse.json({ ok: false, code: "stale", error: "the dossier changed since you opened it", version: cur.version }, { status: 409 });
    const r = applyPatch(cur.dossier, b, s.email);
    if (!r.ok) return NextResponse.json({ ok: false, error: r.error, blockers: r.blockers || [] }, { status: 422 });
    if (!r.changed) return NextResponse.json({ ok: true, version: cur.version, dossier: cur.dossier, errors: r.errors, changed: false });
    const version = await saveDossier(s.ws, r.dossier, cur.version + 1, s.email);
    await logActivity(s, "client_edit", id, `v${version} ${r.dossier.status}${r.status_reset ? " (back to draft)" : ""}`);
    return NextResponse.json({ ok: true, version, dossier: r.dossier, errors: r.errors, status_reset: r.status_reset, changed: true });
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}
