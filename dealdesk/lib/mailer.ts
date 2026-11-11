// Outgoing mail for the deal agent, from the owner's Zoho mailbox over SMTP (SSL, port 465). Used only after the
// owner presses Approve on a specific message in Telegram; nothing else in the system calls it. AGENT_MAIL_LIVE=0
// turns sending off (the approved text is then handed to the owner). A small built-in SMTP client: the deployment
// installs the original package list, so no new dependency is added.
// sendMail is called from lib/sendguard.ts only (emergency stop, opt-out list, idempotency key): do not call it directly.
import tls from "node:tls";
import crypto from "node:crypto";

const EMAIL = /^[^\s@<>,;"]+@[^\s@<>,;"]+\.[a-z]{2,}$/i;
export const mailReady = () => !!(process.env.ZOHO_SMTP_USER && process.env.ZOHO_SMTP_PASS) && process.env.AGENT_MAIL_LIVE !== "0";
const host = () => process.env.ZOHO_SMTP_HOST || "smtp.zoho.com";

type Conn = { cmd: (line: string | null, expect: number) => Promise<string>; end: () => void };
function connect(h: string): Promise<Conn> {
  return new Promise((resolve, reject) => {
    const sock = tls.connect({ host: h, port: Number(process.env.ZOHO_SMTP_PORT || 465), servername: h, timeout: 20000 });
    let buf = "", waiter: ((s: string) => void) | null = null;
    const done = () => { const m = buf.match(/(?:^|\r\n)(\d{3}) [^\r\n]*\r\n$/); if (m && waiter) { const w = waiter; waiter = null; const out = buf; buf = ""; w(out); } };
    sock.on("data", (d) => { buf += d.toString("utf8"); done(); });
    sock.on("timeout", () => { sock.destroy(new Error("SMTP timeout")); });
    const fail = (e: Error) => reject(e);
    sock.once("error", fail);
    const read = () => new Promise<string>((res) => { waiter = res; done(); });
    const cmd = async (line: string | null, expect: number) => {
      if (line !== null) sock.write(line + "\r\n");
      const r = await Promise.race([read(), new Promise<string>((_, rj) => { sock.once("error", rj); sock.once("close", () => rj(new Error("SMTP connection closed"))); })]);
      const lines = r.trim().split("\r\n"), code = Number(lines[lines.length - 1].slice(0, 3));
      if (code !== expect) throw new Error(`SMTP ${code}: ${r.trim().split("\r\n").pop()?.slice(0, 160)}`);
      return r;
    };
    sock.once("secureConnect", () => { sock.off("error", fail); resolve({ cmd, end: () => { try { sock.write("QUIT\r\n"); } catch { /* closing */ } sock.end(); } }); });
  });
}

async function login(h: string, at: (stage: "connect" | "auth") => void = () => {}) {
  at("connect");
  const c = await connect(h);
  await c.cmd(null, 220);
  await c.cmd("EHLO desk.sinder.pro", 250);
  at("auth");
  await c.cmd("AUTH LOGIN", 334);
  await c.cmd(Buffer.from(process.env.ZOHO_SMTP_USER || "").toString("base64"), 334);
  await c.cmd(Buffer.from(process.env.ZOHO_SMTP_PASS || "").toString("base64"), 235);
  return c;
}

/** Sign-in check against the mail server. Sends nothing. */
export async function mailCheck(): Promise<{ ok: boolean; host: string; error?: string }> {
  const h = host();
  try { const c = await login(h); c.end(); return { ok: true, host: h }; }
  catch (e) { return { ok: false, host: h, error: String((e as Error).message || e).slice(0, 200) }; }
}

const b64 = (s: string) => Buffer.from(s, "utf8").toString("base64");
const wrap = (s: string) => s.replace(/.{1,76}/g, "$&\r\n");
const hdr = (s: string) => (/^[\x20-\x7e]*$/.test(s) ? s : `=?UTF-8?B?${b64(s)}?=`);

// Where a send stopped. Everything up to and including "data" (the DATA command, before its 354 answer) means no message
// content was transmitted: the message was definitely not sent. "body" means the content was on the wire when it failed
// (error, timeout, closed connection, or a refusal of the content): the server may or may not have accepted it.
// lib/sendguard.ts turns this into send_failed (safe to retry) or delivery_unknown (never retried blindly).
export type MailStage = "config" | "address" | "connect" | "auth" | "mail_from" | "rcpt" | "data" | "body" | "done";
export type MailResult = { ok: boolean; id?: string; error?: string; stage?: MailStage };

export async function sendMail(m: { to: string; subject: string; text: string }): Promise<MailResult> {
  if (!mailReady()) return { ok: false, error: "mailbox not configured", stage: "config" };
  const to = m.to.trim(), from = String(process.env.ZOHO_SMTP_USER);
  if (!EMAIL.test(to)) return { ok: false, error: "invalid recipient address", stage: "address" };
  const id = `<${crypto.randomUUID()}@${from.split("@")[1] || "sinder.pro"}>`;
  const name = process.env.ZOHO_FROM_NAME ? `${hdr(process.env.ZOHO_FROM_NAME)} <${from}>` : from;
  const msg = [`From: ${name}`, `To: ${to}`, `Reply-To: ${from}`, `Subject: ${hdr(m.subject.replace(/[\r\n]+/g, " ").slice(0, 200))}`,
    `Date: ${new Date().toUTCString()}`, `Message-ID: ${id}`, "MIME-Version: 1.0", "Content-Type: text/plain; charset=UTF-8", "Content-Transfer-Encoding: base64", "",
    wrap(b64(m.text))].join("\r\n");
  let c: Conn | null = null, stage: MailStage = "connect";
  try {
    c = await login(host(), (st) => { stage = st; });
    stage = "mail_from"; await c.cmd(`MAIL FROM:<${from}>`, 250);
    stage = "rcpt"; await c.cmd(`RCPT TO:<${to}>`, 250);
    stage = "data"; await c.cmd("DATA", 354);
    stage = "body"; await c.cmd(msg + "\r\n.", 250);
    stage = "done";  // the server accepted the message: closing the connection cannot turn this into a failure
    try { c.end(); } catch { /* accepted already */ }
    return { ok: true, id, stage };
  } catch (e) {
    try { c?.end(); } catch { /* closing */ }
    if (stage === "done") return { ok: true, id, stage };
    return { ok: false, error: String((e as Error).message || e).slice(0, 200), stage };
  }
}
