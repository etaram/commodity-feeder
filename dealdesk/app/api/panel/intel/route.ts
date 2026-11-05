import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { intel } from "@/lib/intel";

// GET /api/panel/intel?country=KEN,TZA&type=financing_approval,award&origin=news|record&tier=medium
// -> { ok, events (latest 60), timelines (top 30 by recency and size), hypotheses: { research, actionable }, counts, note }
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const p = req.nextUrl.searchParams;
  const clip = (v: string | null) => (v || "").slice(0, 200);
  try {
    return NextResponse.json({ ok: true, ...(await intel({ country: clip(p.get("country")), type: clip(p.get("type")), origin: clip(p.get("origin")), tier: clip(p.get("tier")) })) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
