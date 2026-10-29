import { createHmac, timingSafeEqual } from "crypto";

const SECRET = () => process.env.AUTH_SECRET || "dev-secret-change-me";

export function signSession(email: string, days = 30): string {
  const exp = Date.now() + days * 864e5;
  const body = `${email}|${exp}`;
  const sig = createHmac("sha256", SECRET()).update(body).digest("base64url");
  return Buffer.from(body).toString("base64url") + "." + sig;
}

export function verifySession(token: string | undefined): { email: string } | null {
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
  const [email, exp] = body.split("|");
  if (!email || Number(exp) < Date.now()) return null;
  return { email };
}

export function checkLogin(email: string, passcode: string): boolean {
  const pass = process.env.TEAM_PASSCODE || "";
  if (!pass || passcode !== pass) return false;
  const allowed = (process.env.ALLOWED_EMAILS || "")
    .split(/[\s,;]+/).map((x) => x.trim().toLowerCase()).filter(Boolean);
  if (allowed.length && !allowed.includes(email.trim().toLowerCase())) return false;
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
}
