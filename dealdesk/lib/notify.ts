import { logEvent } from "./log";

// Email to the admin when someone asks for access, sent through Resend (https://resend.com).
// Vercel env: RESEND_API_KEY (required), NOTIFY_EMAIL (who receives, required: no address is kept in the code, and
// without it the notification is skipped and one event is logged), NOTIFY_FROM (optional;
// without a verified domain Resend only sends from onboarding@resend.dev to the account's own email).
// Never throws: a failed email must not fail the sign-up.
const esc = (v: string) => v.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));

/** Who receives owner notifications: NOTIFY_EMAIL only (one or more addresses), never a built-in address. */
export const notifyTo = (): string[] => (process.env.NOTIFY_EMAIL || "").split(/[\s,;]+/).filter((a) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a));

export async function notifyAccessRequest(email: string, name: string, via: string, origin: string) {
  const key = process.env.RESEND_API_KEY;
  if (!key) return;
  const to = notifyTo();
  if (!to.length) { await logEvent("warn", "notify", "NOTIFY_EMAIL is not set: access request notification skipped", "", email); return; }
  const from = process.env.NOTIFY_FROM || "Sinder Deal Desk <onboarding@resend.dev>";
  const link = `${origin}/#users`;
  const html = `<div dir="rtl" style="font-family:Arial,sans-serif;font-size:15px;line-height:1.6">
<p><b>בקשת גישה חדשה ל-Sinder Deal Desk</b></p>
<p>שם: ${esc(name)}<br>מייל: ${esc(email)}<br>דרך: ${via === "google" ? "Google" : "מייל וסיסמה"}</p>
<p>הבקשה ממתינה לאישור שלך. אשר ובחר תפקיד בלשונית "משתמשים":<br><a href="${link}">${link}</a></p></div>`;
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from, to, subject: `Deal Desk: בקשת גישה חדשה - ${name}`, html, text: `בקשת גישה חדשה: ${name} (${email}), דרך ${via}. אישור: ${link}` }),
    });
    if (!r.ok) await logEvent("warn", "notify", `access email failed ${r.status}`, (await r.text()).slice(0, 300), email);
  } catch (e) {
    await logEvent("warn", "notify", "access email failed", String(e).slice(0, 300), email);
  }
}
