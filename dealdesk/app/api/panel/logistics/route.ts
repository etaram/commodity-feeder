import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logisticsFor, logisticsList } from "@/lib/logistics";

// GET: the logistics directory (forwarders, carriers, customs, inspection and import programmes, ports, insurers).
// POST {sector, region, buyerCountry, origins[], originRegions[], title, defence}: who moves, clears and inspects this deal.
export const dynamic = "force-dynamic";
export const maxDuration = 30;

export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try { return NextResponse.json({ ok: true, rows: await logisticsList() }); }
  catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const arr = (v: unknown) => (Array.isArray(v) ? v : []).map((x) => String(x).slice(0, 40)).slice(0, 12);
  try {
    return NextResponse.json({ ok: true, items: await logisticsFor({ sector: String(b.sector || ""), region: String(b.region || ""), buyerCountry: String(b.buyerCountry || "").toUpperCase().slice(0, 3),
      origins: arr(b.origins), originRegions: arr(b.originRegions), title: String(b.title || "").slice(0, 300), defence: !!b.defence }) });
  } catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}
