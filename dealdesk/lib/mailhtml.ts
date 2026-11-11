// The look of an outgoing message: company letterhead, the text as written, and a signature block (name, title,
// firm, address to reply to). Pure text-to-HTML: nothing here sends. The plain text travels alongside as the
// alternative part, so a mail client that shows no HTML still gets the full message. No images and no tracking:
// both hurt deliverability and neither is needed.
import { TEAM } from "@/lib/team";

export const FIRM = "S-Tier Group";
const INK = "#1b2420", GREEN = "#0f3d2e", BRASS = "#a8843a", MUTED = "#6b756f", RULE = "#e3e6e1";
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const link = (s: string) => esc(s).replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)\]])/g, `<a href="$1" style="color:${GREEN}">$1</a>`);

export type Signer = { name: string; title: string };

/** Splits a closing signature ("Mei Lin Zhang, Supplier Relations ..., S-Tier Group", on one line or several) off the text. */
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
<div style="font-family:Georgia,'Times New Roman',serif;font-size:14px;color:${GREEN};padding-top:8px">${FIRM}</div>
<div style="font-size:13px;padding-top:2px"><a href="mailto:${esc(m.from)}" style="color:${MUTED};text-decoration:none">${esc(m.from)}</a></div>
</td></tr></table>` : "";
  return `<!doctype html><html lang="${rtl ? "he" : "en"}" dir="${dir}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f1">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f3f4f1"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid ${RULE}">
<tr><td dir="ltr" style="padding:22px 32px 16px 32px;border-bottom:2px solid ${GREEN};text-align:${side}">
<span style="font-family:Georgia,'Times New Roman',serif;font-size:22px;letter-spacing:0.5px;color:${GREEN}">${FIRM}</span></td></tr>
<tr><td dir="${dir}" style="padding:28px 32px 30px 32px;font-family:${font};font-size:15px;line-height:1.6;color:${INK};text-align:${side}">
${paras}${sig}</td></tr>
</table></td></tr></table></body></html>`;
}
