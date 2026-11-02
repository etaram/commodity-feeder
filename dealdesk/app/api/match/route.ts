import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { getProfile } from "@/lib/profiles";
import { matches } from "@/lib/match";

// The signed-in user's personal matches: ?mode=focus|broad&limit=150, or ?saved=1 for the watchlist.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const p = await getProfile(s.email).catch(() => null);
  if (!p) return NextResponse.json({ ok: true, profile: false, total: 0, items: [] });
  const q = req.nextUrl.searchParams;
  const mode = q.get("mode") === "broad" ? "broad" : q.get("mode") === "focus" ? "focus" : undefined;
  const r = q.get("saved") ? await matches(p, { ids: p.saved, limit: 500 }) : await matches(p, { mode, limit: Number(q.get("limit")) || 150 });
  return NextResponse.json({ ok: true, profile: true, mode: mode || p.mode, ...r });
}
