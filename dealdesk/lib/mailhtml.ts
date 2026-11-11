// The look of an outgoing message: company letterhead, the text as written, and a signature block (name, title,
// firm, address to reply to). Pure text-to-HTML: nothing here sends. The plain text travels alongside as the
// alternative part, so a mail client that shows no HTML still gets the full message. // One small image (the logo mark, served from our own site); the firm name next to it is live text, so the
// header reads correctly when a mail client blocks images. No tracking.
import { TEAM } from "@/lib/team";

export const FIRM = "Sinder";
export const TAGLINE = process.env.MAIL_TAGLINE || "Everything you need";
// Brand colours of the logo (public/brand): navy and gold.
const INK = "#1c2433", GREEN = "#172b4d", BRASS = "#b8902e", MUTED = "#526175", RULE = "#e2e5ea";
const site = () => (process.env.MAIL_SITE_URL || "https://sinder.pro").replace(/\/+$/, "");
const logo = () => process.env.MAIL_LOGO_URL || "https://desk.sinder.pro/brand/mark-mail.gif";
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const link = (s: string) => esc(s).replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)\]])/g, `<a href="$1" style="color:${GREEN}">$1</a>`);

export type Signer = { name: string; title: string };

/** Splits a closing signature ("Mei Lin Zhang, Supplier Relations ..., Sinder", on one line or several) off the text. */
export function splitSignature(text: string): { body: string; signer: Signer | null } {
  const lines = text.replace(/\r/g, "").trimEnd().split("\n");
  for (let i = lines.length - 1; i >= Math.max(0, lines.length - 5); i--) {
    const m = TEAM.find((t) => lines[i].trim().startsWith(t.name));
    if (!m) continue;
    let from = i;
    while (from > 0 && /^(best|kind|warm)?\s*regards,?$|^sincerely,?$|^thanks?( you)?,?$|^בברכה,?$/i.test(lines[from - 1].trim())) from--;
    const closing = lines.slice(from, i).join("\n").trim();
    return { body: (lines.slice(0, from).join("\n").trimEnd() + (closing ? "\n\n" + closing : "")).trim(), signer: { name: m.name, title: m.title } };
  }
  return { body: text.trim(), signer: null };
}

export function renderMail(m: { text: string; from: string; fromName?: string; fromTitle?: string }): string {
  const { body, signer } = splitSignature(m.text);
  const who: Signer | null = signer || (m.fromName ? { name: m.fromName, title: m.fromTitle || "" } : null);
  const rtl = /[֐-׿؀-ۿ]/.test(body.slice(0, 400));
  const dir = rtl ? "rtl" : "ltr", side = rtl ? "right" : "left";
  const font = "Arial,Helvetica,sans-serif";
  const paras = body.split(/\n{2,}/).map((p) => `<p style="margin:0 0 16px 0">${link(p.trim()).replace(/\n/g, "<br>")}</p>`).join("");
  const sig = who ? `<table role="presentation" cellpadding="0" cellspacing="0" border="0" dir="${dir}" style="margin-top:28px"><tr>
<td style="border-${side}:3px solid ${BRASS};padding-${side}:14px;font-family:${font};text-align:${side}">
<div style="font-size:15px;font-weight:bold;color:${INK}">${esc(who.name)}</div>
${who.title ? `<div style="font-size:13px;color:${MUTED};padding-top:2px">${esc(who.title)}</div>` : ""}
<div style="font-size:13px;font-weight:bold;letter-spacing:1px;color:${GREEN};padding-top:8px">SINDER</div>
<div style="font-size:13px;padding-top:2px"><a href="mailto:${esc(m.from)}" style="color:${MUTED};text-decoration:none">${esc(m.from)}</a></div>
<div style="font-size:13px;padding-top:2px"><a href="${esc(site())}" style="color:${GREEN}">${esc(site().replace(/^https?:\/\//, ""))}</a></div>
</td></tr></table>` : "";
  return `<!doctype html><html lang="${rtl ? "he" : "en"}" dir="${dir}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f1">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f3f4f1"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid ${RULE}">
<tr><td dir="ltr" style="padding:22px 32px 16px 32px;border-bottom:2px solid ${BRASS};text-align:${side}">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" dir="ltr" align="${side}"><tr>
<td style="vertical-align:middle"><a href="${esc(site())}"><img src="${esc(logo())}" width="44" height="44" alt="S" style="display:block;border:0;border-radius:10px;background-color:#172b4d;color:#e8c56f;font-family:Georgia,serif;font-size:26px;font-weight:bold;line-height:44px;text-align:center"></a></td>
<td style="vertical-align:middle;padding-left:12px;font-family:${font};text-align:left">
<a href="${esc(site())}" style="text-decoration:none;font-size:22px;line-height:24px;font-weight:bold;letter-spacing:2px;color:${GREEN}">SINDER</a>
<div style="font-size:12px;line-height:16px;letter-spacing:0.4px;color:${BRASS};padding-top:2px">${esc(TAGLINE)}</div></td></tr></table></td></tr>
<tr><td dir="${dir}" style="padding:28px 32px 30px 32px;font-family:${font};font-size:15px;line-height:1.6;color:${INK};text-align:${side}">
${paras}${sig}</td></tr>
</table></td></tr></table></body></html>`;
}
