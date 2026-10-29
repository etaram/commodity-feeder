import { NextRequest, NextResponse } from "next/server";
import { checkLogin, signSession } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const { email, passcode } = await req.json().catch(() => ({}));
  if (typeof email !== "string" || typeof passcode !== "string" || !checkLogin(email, passcode)) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set("dd_session", signSession(email.trim()), { httpOnly: true, secure: true, sameSite: "lax", maxAge: 30 * 86400, path: "/" });
  return res;
}
