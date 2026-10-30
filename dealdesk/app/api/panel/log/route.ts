import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { logEvent } from "@/lib/log";

// Browser-side errors from the panel (script errors, failed calls). Signed-in users only, a few per minute per instance.
let bucket = 0, win = 0;
export async function POST(req: NextRequest) {
  const s = verifySession((await cookies()).get("dd_session")?.value);
  if (!s) return NextResponse.json({ ok: false }, { status: 401 });
  const now = Date.now();
  if (now - win > 60_000) { win = now; bucket = 0; }
  if (++bucket > 20) return NextResponse.json({ ok: true, dropped: true });
  const b = await req.json().catch(() => ({}));
  await logEvent(b.level === "warn" ? "warn" : "error", "browser", b.message, `${b.where || ""} | ${b.ua || ""}`, s.email);
  return NextResponse.json({ ok: true });
}
