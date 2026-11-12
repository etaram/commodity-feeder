import { NextRequest, NextResponse } from "next/server";
import { findUser, normEmail, validEmail } from "@/lib/users";
import { sendMail, mailReady } from "@/lib/mailer";
import { loginKeys, loginLimiter } from "@/lib/ratelimit";
import { logActivity } from "@/lib/activity";
import { resetBase, resetToken, RESET_MINUTES } from "@/lib/reset";

// "Forgot password": e-mails a one-time link to the address of an active account. The answer is the same whether or
// not the account exists (no account discovery), and requests count against the same limiter as failed sign-ins.
export async function POST(req: NextRequest) {
  const { email } = await req.json().catch(() => ({}));
  const e = normEmail(String(email || ""));
  const same = NextResponse.json({ ok: true, minutes: RESET_MINUTES });
  if (!validEmail(e)) return NextResponse.json({ ok: false, error: "Enter the e-mail address of your account." }, { status: 400 });
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "";
  const k = loginKeys(ip, e);
  if (loginLimiter.retryAfter(k.ip) || loginLimiter.retryAfter(k.email)) return NextResponse.json({ ok: false, code: "rate_limited", error: "Too many attempts. Try again later." }, { status: 429 });
  loginLimiter.fail(k.ip); loginLimiter.fail(k.email);
  if (!mailReady()) return NextResponse.json({ ok: false, error: "Password reset by e-mail is not available here." }, { status: 503 });
  const u = await findUser(e, true).catch(() => null);
  if (!u || u.status !== "active") return same;
  const link = `${resetBase()}/login/reset?t=${encodeURIComponent(resetToken(u.email, u.pass_hash || ""))}`;
  const r = await sendMail({ to: u.email, subject: "Sinder Deal Desk: set a new password",
    text: `Someone (hopefully you) asked to set a new password for ${u.email} on the Sinder Deal Desk.\n\nOpen this link within ${RESET_MINUTES} minutes to choose a new password:\n${link}\n\nThe link works once. If you did not ask for this, ignore this message; your password stays as it is.` });
  await logActivity({ email: u.email, name: u.name, role: u.role }, "password_reset_requested", "", r.ok ? "sent" : `failed ${r.stage || ""}`).catch(() => {});
  return same;
}
