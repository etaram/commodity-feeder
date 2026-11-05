import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { coverage } from "@/lib/coverage";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// GET -> {rows}: the coverage-gap radar over the priority products (lib/coverage.ts). ?fresh=1 recomputes.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    return NextResponse.json({ ok: true, rows: await coverage(req.nextUrl.searchParams.get("fresh") === "1") });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
