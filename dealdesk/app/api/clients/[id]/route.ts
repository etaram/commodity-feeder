import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { applyPatch, canApprove, KIND_OF, loadDossier, outreachClaims, prioritizeQuestions, reviewState, saveDossier, technicalOf, type Dossier, type Patch } from "@/lib/dossier";
import type { Session } from "@/lib/auth";

export const dynamic = "force-dynamic";
type Ctx = { params: Promise<{ id: string }> };
const notFound = () => NextResponse.json({ ok: false, error: "client not found" }, { status: 404 });

// What the screen needs besides the stored dossier, all computed in code from the dossier itself.
const view = (d: Dossier, s: Session) => ({ review_state: reviewState(d), questions: prioritizeQuestions(d), outreach_claims: outreachClaims(d).map((c) => c.id), technical: technicalOf(d.claims),
  kind_of: KIND_OF, can_approve: canApprove(d, s), is_admin: s.role === "admin", outreach: { enabled: false, reason: "Outreach needs an approved conversation: not available from this page" } });

// GET /api/clients/:id -> {ok, version, dossier, review_state, questions (prioritised, incl. the technical template),
//   outreach_claims, technical, kind_of, can_approve, outreach:{enabled:false}}
// The workspace comes from the session. A client id of another workspace returns 404, exactly like an id that does
// not exist (rows are read by workspace AND client id).
export async function GET(_req: NextRequest, { params }: Ctx) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const { id } = await params;
  try {
    const cur = await loadDossier(s.ws, id);
    if (!cur) return notFound();
    return NextResponse.json({ ok: true, version: cur.version, dossier: cur.dossier, ...view(cur.dossier, s) });
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}

// PUT /api/clients/:id {version, ...Patch} (see lib/dossier.ts Patch): edit fields and claims, approve, reject, verify,
// resolve contradictions, answer questions, mandate, change status (draft -> reviewed -> active). 409 when version is
// stale. Approving a claim, changing the mandate and activating need an admin or this client's representative; the
// role is read from the session here, never from the body. 403 when a patch asked only for things the caller may not do.
export async function PUT(req: NextRequest, { params }: Ctx) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const { id } = await params;
  const b = (await req.json().catch(() => ({}))) as Patch & { version?: number };
  try {
    const cur = await loadDossier(s.ws, id);
    if (!cur) return notFound();
    if (b.version !== undefined && Number(b.version) !== cur.version) return NextResponse.json({ ok: false, code: "stale", error: "the dossier changed since you opened it", version: cur.version }, { status: 409 });
    if (b.status === "active" && !canApprove(cur.dossier, s)) return NextResponse.json({ ok: false, code: "forbidden", error: "only an admin or this client's representative can approve a client for outreach preparation" }, { status: 403 });
    const r = applyPatch(cur.dossier, b, s.email, { email: s.email, role: s.role });
    if (!r.ok) return NextResponse.json({ ok: false, error: r.error, blockers: r.blockers || [] }, { status: 422 });
    if (!r.changed && r.errors.length && r.errors.every((e) => /only an admin/.test(e))) return NextResponse.json({ ok: false, code: "forbidden", error: r.errors[0], errors: r.errors }, { status: 403 });
    if (!r.changed) return NextResponse.json({ ok: true, version: cur.version, dossier: cur.dossier, errors: r.errors, changed: false, ...view(cur.dossier, s) });
    const version = await saveDossier(s.ws, r.dossier, cur.version + 1, s.email);
    await logActivity(s, "client_edit", id, `v${version} ${r.dossier.status}${r.status_reset ? " (back to draft)" : ""}`);
    return NextResponse.json({ ok: true, version, dossier: r.dossier, errors: r.errors, status_reset: r.status_reset, changed: true, ...view(r.dossier, s) });
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}
