// Outgoing mail for the deal agent, from the owner's Zoho mailbox over SMTP. Used only after the owner presses
// Approve on a specific message in Telegram; nothing else in the system calls it. AGENT_MAIL_LIVE=0 turns sending
// off (the approved text is then handed to the owner, as before).
import nodemailer from "nodemailer";

const EMAIL = /^[^\s@<>,;]+@[^\s@<>,;]+\.[a-z]{2,}$/i;
export const mailReady = () => !!(process.env.ZOHO_SMTP_USER && process.env.ZOHO_SMTP_PASS) && process.env.AGENT_MAIL_LIVE !== "0";

function transport(host = process.env.ZOHO_SMTP_HOST || "smtp.zoho.com") {
  return nodemailer.createTransport({ host, port: 465, secure: true, auth: { user: process.env.ZOHO_SMTP_USER, pass: process.env.ZOHO_SMTP_PASS },
    connectionTimeout: 15000, greetingTimeout: 15000, socketTimeout: 30000 });
}

/** Sign-in check against the mail server. Sends nothing. */
export async function mailCheck(): Promise<{ ok: boolean; host: string; error?: string }> {
  const host = process.env.ZOHO_SMTP_HOST || "smtp.zoho.com";
  try { await transport(host).verify(); return { ok: true, host }; }
  catch (e) { return { ok: false, host, error: String((e as Error).message || e).slice(0, 200) }; }
}

export async function sendMail(m: { to: string; subject: string; text: string }): Promise<{ ok: boolean; id?: string; error?: string }> {
  if (!mailReady()) return { ok: false, error: "mailbox not configured" };
  const to = m.to.trim();
  if (!EMAIL.test(to)) return { ok: false, error: "invalid recipient address" };
  const from = process.env.ZOHO_SMTP_USER!;
  try {
    const r = await transport().sendMail({ from: process.env.ZOHO_FROM_NAME ? `"${process.env.ZOHO_FROM_NAME}" <${from}>` : from, to, subject: m.subject.slice(0, 200), text: m.text, replyTo: from });
    return { ok: true, id: r.messageId };
  } catch (e) { return { ok: false, error: String((e as Error).message || e).slice(0, 200) }; }
}
