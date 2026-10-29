import { NextRequest, NextResponse } from "next/server";

// Verifies the signed session cookie (HMAC-SHA256 with AUTH_SECRET, same format as lib/auth.ts) on every request.
const b64url = (buf: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function valid(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const [b, sig] = token.split(".");
  if (!b || !sig) return false;
  try {
    const body = atob(b.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = Number(body.split("|")[1]);
    if (!Number.isFinite(exp) || exp < Date.now()) return false;
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(process.env.AUTH_SECRET || "dev-secret-change-me"), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const expect = b64url(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body)));
    if (expect.length !== sig.length) return false;
    let diff = 0;
    for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expect.charCodeAt(i);
    return diff === 0;
  } catch {
    return false;
  }
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/login") || pathname.startsWith("/api/login") || pathname.startsWith("/_next") || pathname === "/favicon.ico") {
    return NextResponse.next();
  }
  if (!(await valid(req.cookies.get("dd_session")?.value))) {
    if (pathname.startsWith("/api/")) return NextResponse.json({ ok: false, error: "signed out" }, { status: 401 });
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image).*)"] };
