import { createHmac, timingSafeEqual } from "crypto";

// Password reset by e-mail. The link carries base64url("email|expiry") + "." + HMAC over that body AND the account's
// current password hash, keyed by AUTH_SECRET: no new secret, nothing stored, valid 30 minutes, and single-use, since
// setting a new password changes the hash and so invalidates every link issued before it.
const KEY = () => { const s = process.env.AUTH_SECRET || ""; if (s.length < 16) throw new Error("AUTH_SECRET is not set"); return s; };
const mac = (body: string, passHash: string) => createHmac("sha256", KEY()).update(`dd-reset-v1|${body}|${passHash}`).digest("base64url");
export const RESET_MINUTES = 30;

export function resetToken(email: string, passHash: string, now = Date.now()): string {
  const body = `${email}|${now + RESET_MINUTES * 60e3}`;
  return Buffer.from(body).toString("base64url") + "." + mac(body, passHash);
}
// The e-mail the token names, before the account is read (the signature is checked by checkReset)
export function resetEmail(token: string): string {
  const [b] = String(token || "").split(".");
  try { return Buffer.from(b || "", "base64url").toString().split("|")[0] || ""; } catch { return ""; }
}
export function checkReset(token: string, passHash: string, now = Date.now()): { ok: true; email: string } | { ok: false; why: "malformed" | "expired" | "invalid" } {
  const [b, sig] = String(token || "").split(".");
  if (!b || !sig) return { ok: false, why: "malformed" };
  const body = Buffer.from(b, "base64url").toString();
  const [email, exp] = body.split("|");
  if (!email || !Number(exp)) return { ok: false, why: "malformed" };
  const want = mac(body, passHash);
  let same = false;
  try { same = timingSafeEqual(Buffer.from(sig), Buffer.from(want)); } catch { same = false; }
  if (!same) return { ok: false, why: "invalid" };
  if (Number(exp) < now) return { ok: false, why: "expired" };
  return { ok: true, email };
}
// Where the link points: a fixed address, never the request's Host header (which a caller could set)
export const resetBase = () => (process.env.DESK_PUBLIC_URL || "https://desk.sinder.pro").replace(/\/+$/, "");
