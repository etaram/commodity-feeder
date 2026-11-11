import { createHmac, timingSafeEqual } from "crypto";

// No default secret in production: a missing AUTH_SECRET must stop sign-in, not fall back to a value anyone can read in the code.
const SECRET = () => {
  const s = process.env.AUTH_SECRET || "";
  if (s) return s;
  if (process.env.NODE_ENV === "production") throw new Error("AUTH_SECRET is not set");
  return "dev-secret-change-me";
};

// Roles, from least to most access. viewer: read only. analyst: also runs research, decisions and projects.
// admin: also approves outside actions (project approvals, closing projects) and manages users.
export type Role = "viewer" | "analyst" | "admin";
export const ROLES: Role[] = ["viewer", "analyst", "admin"];
const RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2 };

// ws: the organisation (workspace) the user belongs to. Private data (deals, the owner's network, client material)
// is scoped by it on the server; it is signed into the session and re-checked against the Users tab (lib/gate.ts),
// never taken from the client. Legacy tokens and the bootstrap team login belong to the original workspace.
export const DEFAULT_WS = "sinder";
export type Session = { email: string; role: Role; name: string; ws: string };
export const asWs = (v: unknown) => (/^[a-z0-9][a-z0-9-]{1,39}$/.test(String(v || "")) ? String(v) : DEFAULT_WS);

export function asRole(v: unknown): Role {
  return ROLES.includes(v as Role) ? (v as Role) : "viewer";
}

// Session token: base64url("email|exp|role|name") + "." + HMAC. The middleware checks the signature and expiry (field 2);
// the role and name are read here on the server only.
export function signSession(email: string, role: Role = "viewer", name = "", days = 30, ws = DEFAULT_WS): string {
  const exp = Date.now() + days * 864e5;
  const body = `${email}|${exp}|${role}|${name.replace(/[|\r\n]/g, " ").slice(0, 80)}|${asWs(ws)}`;
  const sig = createHmac("sha256", SECRET()).update(body).digest("base64url");
  return Buffer.from(body).toString("base64url") + "." + sig;
}

export function verifySession(token: string | undefined): Session | null {
  if (!token) return null;
  const [b, sig] = token.split(".");
  if (!b || !sig) return null;
  const body = Buffer.from(b, "base64url").toString();
  const expect = createHmac("sha256", SECRET()).update(body).digest("base64url");
  try {
    if (!timingSafeEqual(Buffer.from(sig), Buffer.from(expect))) return null;
  } catch {
    return null;
  }
  const [email, exp, role, name, ws] = body.split("|");
  if (!email || Number(exp) < Date.now()) return null;
  // Tokens issued before roles existed carry no role: treated as admin, since only the shared team login existed then.
  return { email, role: role ? asRole(role) : "admin", name: name || "", ws: asWs(ws) };
}

export function hasRole(s: Session | null, min: Role): boolean {
  return !!s && RANK[s.role] >= RANK[min];
}

// The original shared team login (TEAM_USER + TEAM_PASSCODE). Kept as the bootstrap admin account so the owner can
// never be locked out; personal accounts live in the Users tab (lib/users.ts).
export function checkLegacyLogin(user: string, passcode: string): boolean {
  const pass = process.env.TEAM_PASSCODE || "";
  if (!pass || passcode.length !== pass.length) return false;
  try {
    if (!timingSafeEqual(Buffer.from(passcode), Buffer.from(pass))) return false;
  } catch {
    return false;
  }
  const teamUser = (process.env.TEAM_USER || "").trim().toLowerCase();
  if (teamUser) return user.trim().toLowerCase() === teamUser;
  const allowed = (process.env.ALLOWED_EMAILS || "")
    .split(/[\s,;]+/).map((x) => x.trim().toLowerCase()).filter(Boolean);
  return !allowed.length || allowed.includes(user.trim().toLowerCase());
}

export const COOKIE = { httpOnly: true, secure: true, sameSite: "lax" as const, maxAge: 30 * 86400, path: "/" };
