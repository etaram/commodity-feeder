import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { listClients, manualClaim, mergeClaims, newDossier, saveDossier, type Claim } from "@/lib/dossier";

export const dynamic = "force-dynamic";

// GET /api/clients: the clients of the caller's workspace (latest version of each dossier).
export async function GET() {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try { return NextResponse.json({ ok: true, clients: await listClients(s.ws) }); }
  catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}

// POST /api/clients {legal_name, name?, jurisdiction?, country? (ISO3), website?, domains?: string[], business_objective?,
//   representation_status?: "not_agreed"|"in_discussion"|"agreed"|"own_company", claims?: [{field, value, source_ref}], private_notes?}
// Creates a draft dossier in the caller's workspace (taken from the session, never from the body). Claims without a
// source_ref are rejected and listed; nothing created here is approved.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const name = String(b.name || b.legal_name || "").trim();
  if (!name) return NextResponse.json({ ok: false, error: "the client's legal name is required" }, { status: 400 });
  const d = newDossier({ name, client_kind: b.client_kind, legal_name: b.legal_name || name, domains: Array.isArray(b.domains) ? b.domains : [], country: b.country, jurisdiction: b.jurisdiction, website: b.website, business_objective: b.business_objective, representation_status: b.representation_status }, s.email);
  const rejected: { item: unknown; reason: string }[] = [], add: Claim[] = [];
  for (const x of (Array.isArray(b.claims) ? b.claims : []).slice(0, 100)) { const c = manualClaim(x || {}, s.email); if ("error" in c) rejected.push({ item: x, reason: c.error }); else add.push(c); }
  d.claims = mergeClaims([], add).claims;
  if (Array.isArray(b.private_notes)) d.private_notes = b.private_notes.map((n: unknown) => String(n).slice(0, 1000)).filter(Boolean).slice(0, 50);
  try {
    const version = await saveDossier(s.ws, d, 1, s.email);
    await logActivity(s, "client_create", d.client_id, d.name);
    return NextResponse.json({ ok: true, client_id: d.client_id, version, dossier: d, rejected }, { status: 201 });
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}
