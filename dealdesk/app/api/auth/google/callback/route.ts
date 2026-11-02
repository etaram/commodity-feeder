import { NextRequest, NextResponse } from "next/server";
import { OAuth2Client } from "google-auth-library";
import { COOKIE, signSession } from "@/lib/auth";
import { createUser, findUser, touchLogin } from "@/lib/users";
import { sheetsEnabled } from "@/lib/sheets";
import { logEvent } from "@/lib/log";
import { notifyAccessRequest } from "@/lib/notify";

// Google sends the user back here. A verified Google email that already has an active account signs in; an unknown
// email becomes a pending access request (admin approves it in the panel); pending or disabled accounts are told so.
export async function GET(req: NextRequest) {
  const origin = req.nextUrl.origin;
  const back = (q: string) => NextResponse.redirect(`${origin}/login?${q}`);
  const id = process.env.GOOGLE_CLIENT_ID, secret = process.env.GOOGLE_CLIENT_SECRET;
  if (!id || !secret) return back("err=google");
  const code = req.nextUrl.searchParams.get("code");
  const state = req.nextUrl.searchParams.get("state");
  const want = req.cookies.get("dd_oauth")?.value;
  if (!code || !state || !want || state !== want) return back("err=google");
  try {
    const client = new OAuth2Client(id, secret, `${origin}/api/auth/google/callback`);
    const { tokens } = await client.getToken(code);
    if (!tokens.id_token) return back("err=google");
    const ticket = await client.verifyIdToken({ idToken: tokens.id_token, audience: id });
    const p = ticket.getPayload();
    const email = String(p?.email || "").toLowerCase();
    if (!email || !p?.email_verified) return back("err=google");
    if (!sheetsEnabled()) return back("err=google");

    let u = await findUser(email, true);
    if (!u) {
      u = await createUser(email, String(p.name || email.split("@")[0]), "google");
      await logEvent("info", "users", "access request (google)", email, email);
      await notifyAccessRequest(email, u.name || email, "google", origin);
      return back("pending=1");
    }
    if (u.status !== "active") return back(u.status === "disabled" ? "disabled=1" : "pending=1");
    touchLogin(u.email);
    const res = NextResponse.redirect(`${origin}/`);
    res.cookies.set("dd_session", signSession(u.email, u.role, u.name || String(p.name || "")), COOKIE);
    res.cookies.set("dd_oauth", "", { maxAge: 0, path: "/api/auth/google" });
    return res;
  } catch (e) {
    await logEvent("error", "users", "google sign-in failed", String(e).slice(0, 300));
    return back("err=google");
  }
}
