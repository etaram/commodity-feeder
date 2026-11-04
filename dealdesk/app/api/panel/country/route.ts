import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { countryIntel } from "@/lib/country";
import { logActivity } from "@/lib/activity";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// Country intelligence page: public layers only (tenders, projects, awards, imports, plays, news), signed-in users.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const c = String(req.nextUrl.searchParams.get("c") || "").toUpperCase().slice(0, 3);
  if (!/^[A-Z]{3}$/.test(c)) return NextResponse.json({ ok: false, error: "country is a 3-letter code" }, { status: 400 });
  try {
    const out = await countryIntel(c);
    await logActivity(s, "country_intel", c, `${out.open} open, ${out.plays.length} plays`);
    return NextResponse.json(out);
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
