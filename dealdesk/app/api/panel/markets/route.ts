import { gate } from "@/lib/gate";
import { NextResponse } from "next/server";
import { markets } from "@/lib/markets";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try { return NextResponse.json({ ok: true, ...(await markets() as object) }); }
  catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}
