import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { supplierSearch } from "@/lib/panel";
import { logActivity } from "@/lib/activity";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// POST {sector, text, country, region, hs, n}: the best suppliers for one tender from the whole supplier index.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  try {
    const r = await supplierSearch({ sector: String(b.sector || ""), text: String(b.text || "").slice(0, 600), country: String(b.country || ""),
      region: String(b.region || ""), hs: String(b.hs || ""), n: Number(b.n) || 15, originRegion: String(b.originRegion || ""),
      originCountry: String(b.originCountry || "").toUpperCase(), exportersOnly: !!b.exportersOnly, strict: (b.strict ?? !!b.research) === true && process.env.SUPPLIER_STRICT !== "off" });
    await logActivity(s, b.research ? "supplier_research" : "suppliers_for", String(b.text || "").slice(0, 120),
      `${b.sector || ""} | ${b.originRegion || b.originCountry || b.country || ""} | ${r.total} found`);
    return NextResponse.json({ ok: true, ...r });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
