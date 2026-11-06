// Links from Telegram into the system: each opens the right page in the panel (/?open=kind:value).
//   t:<tender id>  d:<deal id>  s:<supplier name>|<ISO3>  c:<ISO3 country page>
export const DESK = process.env.DESK_URL || "https://desk.sinder.pro";
export type OpenKind = "t" | "d" | "s" | "c";
export const openUrl = (k: OpenKind, v: string) => `${DESK}/?open=${k}:${encodeURIComponent(v)}`;
export const tenderUrl = (id: string) => openUrl("t", id);
export const dealUrl = (id: string) => openUrl("d", id);
export const supplierUrl = (name: string, country = "") => openUrl("s", country ? `${name}|${country}` : name);
export const countryUrl = (iso3: string) => openUrl("c", iso3);
const attr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
/** an HTML link for Telegram; text must already be escaped */
export const a = (href: string, text: string) => (href ? `<a href="${attr(href)}">${text}</a>` : text);
/** Escape model text for Telegram HTML and turn [text](https://...) into links (http and https only). */
export function richText(s: string) {
  const esc = (x: string) => x.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
  const out: string[] = [];
  let i = 0;
  const rx = /\[([^\]\n]{1,200})\]\((https?:\/\/[^\s)]{1,500})\)/g;
  for (const m of s.matchAll(rx)) { out.push(esc(s.slice(i, m.index)), a(m[2], esc(m[1]))); i = (m.index || 0) + m[0].length; }
  out.push(esc(s.slice(i)));
  return out.join("");
}
