import { NextRequest, NextResponse } from "next/server";
import { randomBytes } from "crypto";

// Sign in with Google (OpenID Connect). Needs GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in Vercel, with
// https://<site>/api/auth/google/callback registered as an authorized redirect URI on the OAuth client.
export function GET(req: NextRequest) {
  const id = process.env.GOOGLE_CLIENT_ID;
  if (!id) return NextResponse.json({ ok: false, error: "Google sign-in is not configured" }, { status: 404 });
  const state = randomBytes(16).toString("base64url");
  const origin = req.nextUrl.origin;
  const u = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  u.searchParams.set("client_id", id);
  u.searchParams.set("redirect_uri", `${origin}/api/auth/google/callback`);
  u.searchParams.set("response_type", "code");
  u.searchParams.set("scope", "openid email profile");
  u.searchParams.set("state", state);
  u.searchParams.set("prompt", "select_account");
  const res = NextResponse.redirect(u);
  res.cookies.set("dd_oauth", state, { httpOnly: true, secure: true, sameSite: "lax", maxAge: 600, path: "/api/auth/google" });
  return res;
}
