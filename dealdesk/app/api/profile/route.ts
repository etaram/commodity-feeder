import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { cleanProfile, getProfile, saveProfile } from "@/lib/profiles";
import { facets, matches } from "@/lib/match";
import { logActivity } from "@/lib/activity";

// The signed-in user's own profile. GET ?facets=1 also returns what can be picked in the form, and a preview count.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const profile = await getProfile(s.email).catch(() => null);
  const out: Record<string, unknown> = { ok: true, profile };
  if (req.nextUrl.searchParams.get("facets")) out.facets = await facets();
  return NextResponse.json(out);
}

// POST {profile, preview?:true}: preview returns how many items match without saving; otherwise saves.
// POST {hide:id} / {save:id} / {unsave:id}: quick feedback from the lists.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const prev = await getProfile(s.email).catch(() => null);
  if (b.hide || b.save || b.unsave) {
    if (!prev) return NextResponse.json({ ok: false, error: "no profile yet" }, { status: 400 });
    const id = String(b.hide || b.save || b.unsave).slice(0, 120);
    if (b.hide) prev.hidden = [...prev.hidden.filter((x) => x !== id), id].slice(-2000);
    if (b.save) prev.saved = [...prev.saved.filter((x) => x !== id), id].slice(-500);
    if (b.unsave) prev.saved = prev.saved.filter((x) => x !== id);
    await saveProfile(s.email, prev);
    await logActivity(s, b.hide ? "not_relevant" : b.save ? "watch_add" : "watch_remove", id);
    return NextResponse.json({ ok: true, profile: prev });
  }
  const p = cleanProfile(b.profile || {}, prev);
  if (b.preview) {
    const [f, w] = await Promise.all([matches(p, { mode: "focus", limit: 5 }), matches(p, { mode: "broad", limit: 1 })]);
    return NextResponse.json({ ok: true, focus: f.total, broad: w.total, top: f.items.slice(0, 5) });
  }
  await saveProfile(s.email, p);
  await logActivity(s, prev ? "profile_update" : "profile_create", p.lens, `${p.sectors.length} sectors, ${p.countries.length + p.regions.length} places, ${p.mode}`);
  return NextResponse.json({ ok: true, profile: p });
}
