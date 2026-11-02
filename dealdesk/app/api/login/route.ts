import { NextRequest, NextResponse } from "next/server";
import { checkLegacyLogin, COOKIE, signSession } from "@/lib/auth";
import { findUser, touchLogin, verifyPassword } from "@/lib/users";
import { sheetsEnabled } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";

// Email + password. The shared team login (TEAM_USER) signs in as the bootstrap admin; everyone else is looked up
// in the Users tab and must be active. Pending and disabled accounts get a clear code so the login page can explain.
export async function POST(req: NextRequest) {
  const { email, passcode } = await req.json().catch(() => ({}));
  if (typeof email !== "string" || typeof passcode !== "string" || !email.trim() || !passcode) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  if (checkLegacyLogin(email, passcode)) return done(email.trim(), "admin", "Sinder");

  if (!sheetsEnabled()) return NextResponse.json({ ok: false }, { status: 401 });
  const u = await findUser(email).catch(() => null);
  if (!u || !u.pass_hash || !verifyPassword(passcode, u.pass_hash)) {
    if (u) await logActivity({ email: u.email, name: u.name, role: u.role }, "sign_in_failed", "", "wrong password");
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  if (u.status !== "active") { await logActivity({ email: u.email, name: u.name, role: u.role }, "sign_in_blocked", "", u.status); return NextResponse.json({ ok: false, code: u.status }, { status: 403 }); }
  touchLogin(u.email);
  return done(u.email, u.role, u.name);
}

async function done(email: string, role: "viewer" | "analyst" | "admin", name: string) {
  await logActivity({ email, role, name }, "sign_in", "", "password");
  const res = NextResponse.json({ ok: true, role });
  res.cookies.set("dd_session", signSession(email, role, name), COOKIE);
  return res;
}
