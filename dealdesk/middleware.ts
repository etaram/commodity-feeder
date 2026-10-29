import { NextRequest, NextResponse } from "next/server";

// Edge-safe session check: structure + expiry here, full HMAC verification in API routes and pages.
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/login") || pathname.startsWith("/api/login") || pathname.startsWith("/_next") || pathname === "/favicon.ico") {
    return NextResponse.next();
  }
  const token = req.cookies.get("dd_session")?.value;
  const ok = (() => {
    if (!token) return false;
    const [b, sig] = token.split(".");
    if (!b || !sig) return false;
    try {
      const body = atob(b.replace(/-/g, "+").replace(/_/g, "/"));
      const exp = Number(body.split("|")[1]);
      return Number.isFinite(exp) && exp > Date.now();
    } catch {
      return false;
    }
  })();
  if (!ok) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image).*)"] };
