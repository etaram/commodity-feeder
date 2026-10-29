import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { recordDecision } from "@/lib/sheets";

export async function POST(req: NextRequest) {
  const jar = await cookies();
  const session = verifySession(jar.get("dd_session")?.value);
  if (!session) return NextResponse.json({ ok: false }, { status: 401 });
  const { id, decision, title = "", buyer = "", country = "", note = "" } = await req.json().catch(() => ({}));
  if (!id || !["Go", "Watch", "No"].includes(decision)) return NextResponse.json({ ok: false }, { status: 400 });
  try {
    await recordDecision(id, decision, session.email, note, title, buyer, country);
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
