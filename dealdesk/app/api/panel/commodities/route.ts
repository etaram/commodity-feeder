import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { commodityStats } from "@/lib/commodities";

// GET /api/panel/commodities?product=wheat&hs6=1001&limit=100
// -> { ok, items: normalised price rows joined with their stats, worldbank: Pink Sheet monthly series (no filter only), counts, note }
export const dynamic = "force-dynamic";
export const maxDuration = 30;

export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const p = req.nextUrl.searchParams;
  const clip = (v: string | null) => (v || "").slice(0, 120);
  try {
    const limit = parseInt(p.get("limit") || "", 10);
    return NextResponse.json({ ok: true, ...(await commodityStats({ product: clip(p.get("product")), hs6: clip(p.get("hs6")), limit: Number.isFinite(limit) ? limit : undefined })) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
