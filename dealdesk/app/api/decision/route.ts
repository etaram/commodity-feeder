import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { recordDecision } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";

export async function POST(req: NextRequest) {
  const { s: session, res } = await gate("analyst");
  if (!session) return res;
  const { id, decision, title = "", buyer = "", country = "", note = "" } = await req.json().catch(() => ({}));
  if (!id || !["Go", "Watch", "No"].includes(decision)) return NextResponse.json({ ok: false }, { status: 400 });
  try {
    await recordDecision(id, decision, session.email, note, title, buyer, country);
    await logActivity(session, "decision", `${id} ${title}`, `${decision}${note ? ": " + note : ""}`);
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
