import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { financeFor, financeList } from "@/lib/finance";

// GET: the whole financing and grants directory (public institutions, official sources).
// POST {sector, region, buyerCountry, origins[], value, defence}: who can finance this deal, ranked, with reasons and flags.
export const dynamic = "force-dynamic";
export const maxDuration = 30;

export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try { return NextResponse.json({ ok: true, rows: await financeList() }); }
  catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  try {
    const origins = (Array.isArray(b.origins) ? b.origins : []).map((x: unknown) => String(x).toUpperCase().slice(0, 3)).slice(0, 12);
    return NextResponse.json({ ok: true, items: await financeFor({ sector: String(b.sector || ""), region: String(b.region || ""), buyerCountry: String(b.buyerCountry || ""),
      origins, value: Number(b.value) || 0, defence: !!b.defence }) });
  } catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}
