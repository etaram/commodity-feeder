import { NextRequest, NextResponse } from "next/server";
import { COOKIE, signSession } from "@/lib/auth";
import { findUser, hashPassword, updateUser } from "@/lib/users";
import { logActivity } from "@/lib/activity";
import { checkReset, resetEmail } from "@/lib/reset";

// Sets the new password from a valid reset link and signs the person in.
export async function POST(req: NextRequest) {
  const { t, passcode } = await req.json().catch(() => ({}));
  if (typeof passcode !== "string" || passcode.length < 10) return NextResponse.json({ ok: false, error: "Choose a password of at least 10 characters." }, { status: 400 });
  const u = await findUser(resetEmail(String(t || "")), true).catch(() => null);
  const c = u ? checkReset(String(t || ""), u.pass_hash || "") : ({ ok: false, why: "invalid" } as const);
  if (!u || !c.ok) return NextResponse.json({ ok: false, error: !c.ok && c.why === "expired" ? "This link has expired. Ask for a new one." : "This link is not valid any more. Ask for a new one." }, { status: 400 });
  if (u.status !== "active") return NextResponse.json({ ok: false, error: "This account is not active." }, { status: 403 });
  await updateUser(u.email, { pass_hash: hashPassword(passcode) });
  await logActivity({ email: u.email, name: u.name, role: u.role }, "password_reset_done", "", "").catch(() => {});
  const res = NextResponse.json({ ok: true });
  res.cookies.set("dd_session", signSession(u.email, u.role, u.name, 30, u.workspace || undefined), COOKIE);
  return res;
}
