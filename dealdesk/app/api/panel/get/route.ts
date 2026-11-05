import { NextRequest, NextResponse } from "next/server";
import { getRange } from "@/lib/panel";
import { gate } from "@/lib/gate";
import { canRead } from "@/lib/scope";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const { key, fresh } = await req.json().catch(() => ({}));
  // another organisation's private tabs are never served, whatever key the client asks for
  if (!canRead(s.ws, String(key || ""))) return NextResponse.json({ ok: true, values: [[]], at: Date.now(), scoped: true });
  try {
    return NextResponse.json({ ok: true, values: await getRange(String(key || ""), !!fresh), at: Date.now() });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
