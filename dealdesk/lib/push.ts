import { createHmac, createECDH, randomBytes, createCipheriv, createSign, createPrivateKey } from "crypto";
import { appendRow, ENGINE_SHEET, readRanges } from "./sheets";

// Web Push without a library: VAPID (ES256 JWT) + aes128gcm content encoding (RFC 8291), so the same alerts that go
// to Telegram reach the installed app on a phone. Subscriptions live in the hidden tab 'Push'
// (email, endpoint, p256dh, auth, lang, created, ua). A gone endpoint (404/410) is dropped on the next send.
const TAB = "Push";
const b64u = (b: Buffer) => b.toString("base64url");
const fromB64u = (s: string) => Buffer.from(s, "base64url");
export type Sub = { email: string; endpoint: string; p256dh: string; auth: string; lang: "he" | "en" };

export async function subs(): Promise<Sub[]> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:G5000`]).catch(() => null))?.[0] || [];
  const m = new Map<string, Sub>();
  for (const r of rows) if (r && r[1]) m.set(r[1], { email: r[0] || "", endpoint: r[1], p256dh: r[2] || "", auth: r[3] || "", lang: r[4] === "en" ? "en" : "he" });
  return [...m.values()];
}
export async function addSub(email: string, s: { endpoint: string; keys: { p256dh: string; auth: string } }, lang: string, ua: string) {
  await appendRow(TAB, [email, s.endpoint, s.keys.p256dh, s.keys.auth, lang === "en" ? "en" : "he", new Date().toISOString().slice(0, 16), ua.slice(0, 120)]);
}

function vapidJwt(audience: string): string {
  const priv = process.env.VAPID_PRIVATE_KEY || "", pub = process.env.VAPID_PUBLIC_KEY || "";
  const jwk = { kty: "EC", crv: "P-256", d: priv, x: b64u(fromB64u(pub).subarray(1, 33)), y: b64u(fromB64u(pub).subarray(33, 65)) };
  const key = createPrivateKey({ key: jwk, format: "jwk" });
  const head = b64u(Buffer.from(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const body = b64u(Buffer.from(JSON.stringify({ aud: audience, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: process.env.VAPID_SUBJECT || "mailto:admin@sinder.pro" })));
  const sig = createSign("SHA256").update(`${head}.${body}`).sign({ key, dsaEncoding: "ieee-p1363" });
  return `${head}.${body}.${b64u(sig)}`;
}
const hkdf = (salt: Buffer, ikm: Buffer, info: Buffer, len: number) => { const prk = createHmac("sha256", salt).update(ikm).digest(); return createHmac("sha256", prk).update(Buffer.concat([info, Buffer.from([1])])).digest().subarray(0, len); };

function encrypt(sub: Sub, payload: Buffer): Buffer {
  const ua = fromB64u(sub.p256dh), auth = fromB64u(sub.auth);
  const ecdh = createECDH("prime256v1"); const local = ecdh.generateKeys();
  const shared = ecdh.computeSecret(ua);
  const salt = randomBytes(16);
  const prkInfo = Buffer.concat([Buffer.from("WebPush: info\0"), ua, local]);
  const ikm = hkdf(auth, shared, prkInfo, 32);
  const cek = hkdf(salt, ikm, Buffer.from("Content-Encoding: aes128gcm\0"), 16);
  const nonce = hkdf(salt, ikm, Buffer.from("Content-Encoding: nonce\0"), 12);
  const c = createCipheriv("aes-128-gcm", cek, nonce);
  const body = Buffer.concat([c.update(Buffer.concat([payload, Buffer.from([2])])), c.final(), c.getAuthTag()]);
  const rs = Buffer.alloc(4); rs.writeUInt32BE(4096);
  return Buffer.concat([salt, rs, Buffer.from([local.length]), local, body]);
}

export async function sendPush(s: Sub, data: { title: string; body: string; url?: string; tag?: string }): Promise<"ok" | "gone" | "error"> {
  if (!process.env.VAPID_PRIVATE_KEY || !process.env.VAPID_PUBLIC_KEY) return "error";
  const aud = new URL(s.endpoint).origin;
  try {
    const r = await fetch(s.endpoint, { method: "POST", headers: { "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", TTL: "86400", Urgency: "normal",
      Authorization: `vapid t=${vapidJwt(aud)}, k=${process.env.VAPID_PUBLIC_KEY}` }, body: new Uint8Array(encrypt(s, Buffer.from(JSON.stringify(data)))) });
    if (r.status === 404 || r.status === 410) return "gone";
    return r.ok ? "ok" : "error";
  } catch { return "error"; }
}

export async function pushAll(data: { title: string; body: string; url?: string; tag?: string }, lang?: "he" | "en") {
  const all = await subs();
  const out = { ok: 0, gone: 0, error: 0 };
  for (const s of all) { if (lang && s.lang !== lang) continue; out[await sendPush(s, data)]++; }
  return out;
}

