import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { todayGeneral, todayFocus } from "@/lib/focus";

// GET /api/panel/today: the general morning page. GET /api/panel/today?focus=<lens>: the same layers through one lens.
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const focus = req.nextUrl.searchParams.get("focus");
  try {
    return NextResponse.json({ ok: true, ...(focus ? await todayFocus(focus) : await todayGeneral()) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
