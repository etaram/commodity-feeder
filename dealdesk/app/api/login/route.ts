import { NextRequest, NextResponse } from "next/server";
import { checkLegacyLogin, COOKIE, signSession } from "@/lib/auth";
import { findUser, touchLogin, verifyPassword } from "@/lib/users";
import { sheetsEnabled } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";
import { loginKeys, loginLimiter } from "@/lib/ratelimit";

// Email + password. The shared team login (TEAM_USER) signs in as the bootstrap admin; everyone else is looked up
// in the Users tab and must be active. Pending and disabled accounts get a clear code so the login page can explain.
// Failed attempts are limited per IP and per e-mail (lib/ratelimit.ts), the shared team login included: the check
// runs before any password is compared, so a blocked key gets no further guesses, right or wrong.
export async function POST(req: NextRequest) {
  const { email, passcode } = await req.json().catch(() => ({}));
  if (typeof email !== "string" || typeof passcode !== "string" || !email.trim() || !passcode) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim() || "?";
  const k = loginKeys(ip, email);
  const wait = Math.max(loginLimiter.retryAfter(k.ip), loginLimiter.retryAfter(k.email));
  if (wait) {
    const by = [loginLimiter.noteBlocked(k.ip) && "ip", loginLimiter.noteBlocked(k.email) && "email"].filter(Boolean);
    if (by.length) await logActivity({ email: email.trim().slice(0, 120) }, "sign_in_rate_limited", "", `too many failed attempts (${by.join("+")} limit), ip ${ip.slice(0, 60)}`);
    const mins = Math.ceil(wait / 60);
    return NextResponse.json({ ok: false, code: "rate_limited", error: `Too many failed sign-in attempts. Try again in ${mins} minute${mins === 1 ? "" : "s"}.` }, { status: 429, headers: { "Retry-After": String(wait) } });
  }
  const failed = () => { loginLimiter.fail(k.ip); loginLimiter.fail(k.email); return NextResponse.json({ ok: false }, { status: 401 }); };
  // A successful sign-in clears the e-mail counter. The IP counter is left to expire, so one valid account cannot
  // be used to reset the count between guesses at other accounts from the same address.
  if (checkLegacyLogin(email, passcode)) { loginLimiter.clear(k.email); return done(email.trim(), "admin", "Sinder"); }

  if (!sheetsEnabled()) return failed();
  const u = await findUser(email).catch(() => null);
  if (!u || !u.pass_hash || !verifyPassword(passcode, u.pass_hash)) {
    if (u) await logActivity({ email: u.email, name: u.name, role: u.role }, "sign_in_failed", "", "wrong password");
    return failed();
  }
  loginLimiter.clear(k.email);
  if (u.status !== "active") { await logActivity({ email: u.email, name: u.name, role: u.role }, "sign_in_blocked", "", u.status); return NextResponse.json({ ok: false, code: u.status }, { status: 403 }); }
  touchLogin(u.email);
  return done(u.email, u.role, u.name, u.workspace);
}

async function done(email: string, role: "viewer" | "analyst" | "admin", name: string, ws = "") {
  await logActivity({ email, role, name }, "sign_in", "", "password");
  const res = NextResponse.json({ ok: true, role });
  res.cookies.set("dd_session", signSession(email, role, name, 30, ws || undefined), COOKIE);
  return res;
}
