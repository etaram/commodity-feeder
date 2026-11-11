import { selfKey } from "@/lib/selfkey";
import { auditMayCall } from "@/lib/auditscope";
import { NextRequest, NextResponse } from "next/server";

// Verifies the signed session cookie (HMAC-SHA256 with AUTH_SECRET, same format as lib/auth.ts) on every request.
const b64url = (buf: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function valid(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const [b, sig] = token.split(".");
  if (!b || !sig) return false;
  try {
    // atob gives one char per byte: sign those exact bytes (re-encoding as UTF-8 would break non-ASCII names, e.g. Hebrew).
    const bin = atob(b.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    const exp = Number(bin.split("|")[1]);
    if (!Number.isFinite(exp) || exp < Date.now()) return false;
    // fail closed: without AUTH_SECRET in production no session is valid (no readable default secret)
    const secret = process.env.AUTH_SECRET || (process.env.NODE_ENV === "production" ? "" : "dev-secret-change-me");
    if (!secret) return false;
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const expect = b64url(await crypto.subtle.sign("HMAC", key, bytes));
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
  // the MCP endpoint checks its own key in the address (app/api/mcp/[key]); /api/mcp/key itself needs a signed-in admin
  if (pathname.startsWith("/api/mcp/") && pathname !== "/api/mcp/key") return NextResponse.next();
  if (pathname.startsWith("/login") || pathname.startsWith("/api/login") || pathname.startsWith("/api/register") || pathname.startsWith("/api/auth/") || pathname.startsWith("/api/logout") || pathname.startsWith("/api/cron/") || pathname === "/api/telegram" || pathname === "/api/agent/step" || pathname === "/api/health" || pathname.startsWith("/_next") || pathname === "/favicon.ico") {
    // these routes check their own secret and never run under the audit session: the audit header is dropped here, so a
    // route that the middleware lets through cannot be reached as "Audit" through gate()
    if (!req.headers.has("x-dd-audit")) return NextResponse.next();
    const h = new Headers(req.headers); h.delete("x-dd-audit");
    return NextResponse.next({ request: { headers: h } });
  }
  // the self-check (app/api/health) calls the routes with the audit token while AUDIT_TOKEN is set (see lib/gate.ts)
  const audit = process.env.AUDIT_TOKEN || "";
  const given = req.headers.get("x-dd-audit") || "";
  if (given.length >= 32 && ((audit.length >= 32 && given === audit) || given === (await selfKey()))) {
    // the audit session reads; it never sends, approves or changes access (lib/auditscope.ts)
    if (!auditMayCall(req.method, pathname)) return NextResponse.json({ ok: false, code: "audit_read_only", error: "The audit session cannot call this route" }, { status: 403 });
    return NextResponse.next();
  }
  if (!(await valid(req.cookies.get("dd_session")?.value))) {
    if (pathname.startsWith("/api/")) return NextResponse.json({ ok: false, error: "signed out" }, { status: 401 });
    const url = req.nextUrl.clone();
    // a link from Telegram (/?open=t:ID) survives the sign-in: the login page returns to it
    const back = pathname === "/" && req.nextUrl.search ? `/${req.nextUrl.search}` : "";
    url.pathname = "/login";
    url.search = back ? `?next=${encodeURIComponent(back)}` : "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image).*)"] };
