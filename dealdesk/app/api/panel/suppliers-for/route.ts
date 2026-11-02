import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { suppliersFor } from "@/lib/panel";
import { logActivity } from "@/lib/activity";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// POST {sector, text, country, region, hs, n}: the best suppliers for one tender from the whole supplier index.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  try {
    const values = await suppliersFor({ sector: String(b.sector || ""), text: String(b.text || "").slice(0, 600), country: String(b.country || ""),
      region: String(b.region || ""), hs: String(b.hs || ""), n: Number(b.n) || 15 });
    await logActivity(s, "suppliers_for", String(b.text || "").slice(0, 120), `${b.sector || ""} | ${b.country || ""} | ${values.length - 1} found`);
    return NextResponse.json({ ok: true, values });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
