import { NextRequest, NextResponse } from "next/server";
import { getRange } from "@/lib/panel";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  const { key, fresh } = await req.json().catch(() => ({}));
  try {
    return NextResponse.json({ ok: true, values: await getRange(String(key || ""), !!fresh), at: Date.now() });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
