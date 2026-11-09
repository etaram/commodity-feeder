import { anthropicHeaders } from "@/lib/anthropic";
import { appendRow, appendRows, ENGINE_SHEET, lookupContact, readRanges } from "./sheets";
import { listUsers } from "./users";
import { allTenders, searchTendersSmart, supplierSearch, getRange } from "./panel";
import { routeOptions } from "./routes";
import { MODEL } from "./anthropic";
import { countryIntel } from "./country";
import { readBrief, buildBrief } from "./brief";
import { claude } from "./anthropic";
import { logActivity } from "./activity";
import { tgEnv } from "./tgenv";
import { a, countryUrl, supplierUrl, tenderUrl } from "./links";
import { startRun, resume, waitingRun, stopLatest, decide, retryLatest, type Io } from "./dealagent";
import { mailCheck } from "./mailer";

// The deal agent's link to Telegram: messages go out through the bot, each next step is a call to /api/agent/step
// (answered at once, the work runs after the answer), authenticated with the webhook secret.
const BASE = process.env.AGENT_BASE_URL || (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : "https://desk.sinder.pro");
export const agentIo: Io = {
  send: (chat, text, extra) => send(chat, text, extra),
  kick: async (id) => { await fetch(`${BASE}/api/agent/step`, { method: "POST", headers: { "content-type": "application/json", "x-agent-secret": process.env.TELEGRAM_WEBHOOK_SECRET || "" }, body: JSON.stringify({ id }), signal: AbortSignal.timeout(8000) }).catch(() => null); },
};
// The approval buttons need callback_query updates; a webhook set before the agent existed did not ask for them.
// Checked once per instance and widened in place (same URL and secret, no pending update dropped).
let hookChecked = false;
export async function ensureCallbacks() {
  if (hookChecked || !tgEnv().token || !process.env.TELEGRAM_WEBHOOK_SECRET) return;
  hookChecked = true;
  const h = await fetch(API("getWebhookInfo")).then((r) => r.json()).catch(() => null);
  const url = h?.result?.url, allowed: string[] = h?.result?.allowed_updates || [];
  const cmds = (he: boolean) => [["tenders", he ? "מכרזים פתוחים לפי התאמה" : "Open tenders by fit"], ["suppliers", he ? "ספקים מוכחים למוצר" : "Proven suppliers"], ["country", he ? "מודיעין מדינה (קוד 3 אותיות)" : "Country intelligence"],
    ["deal", he ? "סוכן עסקאות: מריץ עסקה מקצה לקצה" : "Deal agent, end to end"], ["brief", he ? "התקציר העולמי של היום" : "Today's world brief"], ["plays", he ? "תזות עסקה" : "Deal theses"], ["new", he ? "שיחה חדשה (שוכח את ההקשר)" : "New conversation"], ["help", he ? "עזרה" : "Help"]].map(([command, description]) => ({ command, description }));
  await fetch(API("setMyCommands"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ commands: cmds(true) }) }).catch(() => null);
  await fetch(API("setMyCommands"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ commands: cmds(false), language_code: "en" }) }).catch(() => null);
  if (url && !allowed.includes("callback_query")) {
    await fetch(API("setWebhook"), { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ url, secret_token: process.env.TELEGRAM_WEBHOOK_SECRET, allowed_updates: ["message", "edited_message", "callback_query"], drop_pending_updates: false }) }).catch(() => null);
  }
}
export async function agentCallback(chatId: string, data: string, queryId: string) {
  await fetch(API("answerCallbackQuery"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ callback_query_id: queryId }) }).catch(() => null);
  const link = (await links()).find((l) => l.chat_id === chatId);
  if (!link) return;
  const he = link.lang === "he";
  const qq = data.match(/^qq:(\d)$/);
  if (qq) { const q = (await lastQuestions(chatId))[Number(qq[1])]; if (q) { await send(chatId, `<i>${esc(q)}</i>`); return handle(chatId, q, ""); } return; }
  const tm = data.match(/^(tn|ts|td):(.+)$/);
  if (tm) {
    const t = await findTender(tm[2]);
    if (!t) return send(chatId, he ? "המכרז כבר לא פתוח במערכת." : "That tender is no longer open in the system.");
    if (tm[1] !== "td") await remember(chatId, `tn:${t.id}`, "");
    if (tm[1] === "tn") { await logActivity({ email: link.email, name: link.name }, "tg_tender", t.id); return sendCard(chatId, tenderDetail(t, he), tenderButtons(t.id, he)); }
    if (tm[1] === "ts") { await typing(chatId); return send(chatId, await tenderSuppliers(t, 6, he)); }
    await startRun(agentIo, { chat: chatId, email: link.email, name: link.name, lang: link.lang, request: `Build a deal on tender ${t.id}: ${t.title_en || t.title} (${t.country}, buyer ${t.buyer})` });
    return send(chatId, he ? "פתחתי סוכן עסקאות על המכרז הזה. אעדכן כאן בכל שלב, ואבקש אישור לפני כל פנייה." : "Opened a deal agent on this tender. I will update you here and ask approval before any message.");
  }
  const m = data.match(/^ag:(ok|no|re):([A-Z0-9]+)$/);
  if (!m) return;
  await decide(agentIo, chatId, m[2], m[1] !== "no", m[1] === "re");
}

// Talking to the Deal Desk from Telegram. A chat is linked to a system user once, with a code the user takes from
// the panel (Settings > Telegram); until then the bot answers only /start. Every answer comes from the system's
// own data; the free-text route uses the AI only to choose which of the same tools to call and to phrase the result,
// with the tool outputs as its only facts. Nothing is sent to anyone else, and nothing is submitted.
// Links live in the hidden tab 'Telegram' (chat_id, email, name, linked_at, lang, alerts).
const API = (m: string) => `https://api.telegram.org/bot${tgEnv().token}/${m}`;
const TAB = "Telegram";
type Link = { chat_id: string; email: string; name: string; lang: "he" | "en"; alerts: string };
const money = (n: number) => (!n ? "" : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : `$${Math.round(n / 1e3)}K`);
const esc = (s: string) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));

export async function send(chatId: string, text: string, extra: Record<string, unknown> = {}) {
  if (!tgEnv().token) return;
  for (const part of chunk(text)) {
    await fetch(API("sendMessage"), { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: part, parse_mode: "HTML", disable_web_page_preview: true, ...extra }) }).catch(() => null);
  }
}
function chunk(t: string): string[] { const out: string[] = []; let s = t; while (s.length > 3800) { let i = s.lastIndexOf("\n", 3800); if (i < 1000) i = 3800; out.push(s.slice(0, i)); s = s.slice(i); } out.push(s); return out; }

let linkCache: { at: number; v: Link[] } | null = null;
export async function links(fresh = false): Promise<Link[]> {
  if (!fresh && linkCache && Date.now() - linkCache.at < 60_000) return linkCache.v;
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:F2000`]).catch(() => null))?.[0] || [];
  const m = new Map<string, Link>();
  for (const r of rows) if (r && r[0]) m.set(String(r[0]), { chat_id: String(r[0]), email: r[1] || "", name: r[2] || "", lang: r[4] === "en" ? "en" : "he", alerts: r[5] || "on" });
  linkCache = { at: Date.now(), v: [...m.values()] };
  return linkCache.v;
}

// The link code is derived from the user's email and the bot token, so the panel can show it without a store:
// first 6 chars of a hash. The code is private to the signed-in user; the bot checks it against the active users.
export async function linkCode(email: string): Promise<string> {
  const { createHmac } = await import("crypto");
  return createHmac("sha256", tgEnv().token || "x").update(email.toLowerCase()).digest("hex").slice(0, 6).toUpperCase();
}

async function linkChat(chatId: string, code: string, lang: "he" | "en"): Promise<string> {
  const users = (await listUsers(true)).filter((u) => u.status === "active");
  // the shared team login (TEAM_USER) has no Users row but signs in to the panel and sees its own code
  const team = (process.env.TEAM_USER || "").trim().toLowerCase();
  if (team && !users.some((u) => u.email.toLowerCase() === team)) users.push({ email: team, name: "Sinder", role: "admin", status: "active" } as (typeof users)[number]);
  for (const u of users) {
    if ((await linkCode(u.email)) === code.toUpperCase()) {
      await appendRow(TAB, [chatId, u.email, u.name || "", new Date().toISOString().slice(0, 16), lang, "on"]);
      await logActivity({ email: u.email, name: u.name, role: u.role }, "telegram_link", chatId, "");
      return lang === "he" ? `מקושר ל-${u.name || u.email}. שלח /help לרשימת הפקודות.` : `Linked to ${u.name || u.email}. Send /help for the commands.`;
    }
  }
  return lang === "he" ? "קוד לא מוכר. הקוד מופיע במערכת: היום בשבילך > טלגרם, בתחתית העמוד." : "Unknown code. The code is shown in the panel: Today for you > Telegram, at the bottom.";
}

const HELP_HE = `פקודות:
/tenders <מילים> [מדינה] - מכרזים פתוחים, לפי התאמה
/country <קוד מדינה> - מודיעין מדינה
/plays [מדינה] - תזות עסקה
/suppliers <מוצר> - ספקים מוכחים
/brief - התקציר העולמי של היום
/alerts on|off - התראות (תזות בביטחון גבוה, תקציר)
/deal <בקשה> - סוכן עסקאות: מריץ עסקה מההתחלה עד הסוף ומבקש אישור לפני כל פנייה
/stop - עצירת הסוכן
/retry - המשך ריצה שנעצרה בתקלה
/new - שיחה חדשה
/mailcheck - בדיקת החיבור לתיבת המייל (לא שולח)
או פשוט לכתוב שאלה או בקשה, למשל: "תמצא לי 5,000 טון תירס לבן לקניה".`;
const HELP_EN = `Commands:
/tenders <words> [ISO3] - open tenders by fit
/country <ISO3> - country intelligence
/plays [ISO3] - deal theses
/suppliers <product> - proven suppliers
/brief - today's world brief
/alerts on|off
/deal <request> - deal agent: runs a deal end to end, asks approval before any message
/stop - stop the agent
/retry - continue a run that stopped on an error
/new - new conversation
/mailcheck - check the mailbox sign-in (sends nothing)
Or just write a question or a request.`;

type Row = Record<string, string>;
const toObjects = (g: string[][]): Row[] => { const h = g[0] || []; return g.slice(1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ""]))); };

// ---- formatting: one card per item, the same labels in every answer -------------------------------------------
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, "")); return Number.isFinite(n) ? n : 0; };
const daysLeft = (dl: string) => { const d = Date.parse(dl); return Number.isFinite(d) ? Math.ceil((d - Date.now()) / 864e5) : null; };
const due = (dl: string, he: boolean) => { const d = daysLeft(dl); return d === null ? "" : d <= 0 ? (he ? "נסגר היום" : "closes today") : he ? `נסגר בעוד ${d} ימים` : `closes in ${d} days`; };
const pct = (v: unknown) => { const n = num(v); return n ? `${Math.round(n <= 1 ? n * 100 : n)}%` : ""; };
export async function typing(chatId: string) { if (tgEnv().token) await fetch(API("sendChatAction"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ chat_id: chatId, action: "typing" }) }).catch(() => null); }
async function sendCard(chatId: string, text: string, keyboard?: { text: string; callback_data: string }[][]) { return send(chatId, text, keyboard ? { reply_markup: { inline_keyboard: keyboard } } : {}); }
const cb = (k: string, id: string) => `${k}:${id}`.slice(0, 64);
async function findTender(id: string) { const { rows, byId } = await allTenders(); return (byId.get(id) || rows.find((r) => r.id.startsWith(id))) as unknown as Row | undefined; }
const tenderButtons = (id: string, he: boolean) => [[{ text: he ? "ספקים מתאימים" : "Matching suppliers", callback_data: cb("ts", id) }, { text: he ? "בנה עסקה" : "Build a deal", callback_data: cb("td", id) }]];

function tenderLine(r: Row, i: number, he: boolean) {
  const title = esc(r.title_en || r.title || "");
  const facts = [esc(r.buyer || ""), esc(r.country || ""), money(num(r.est_value_usd)), due(r.deadline || "", he), r.fit || r.score ? `${he ? "התאמה" : "fit"} ${esc(r.fit || r.score)}` : ""].filter(Boolean).join(" · ");
  return `<b>${i}. ${r.id ? a(tenderUrl(r.id), title) : title}</b>\n${facts}`;
}
async function tenderList(q: string, cty: string, n: number, he: boolean) {
  const res = await searchTendersSmart(q, cty); const rows = res.rows.slice(0, n);
  if (!rows.length) return { text: he ? `לא מצאתי מכרזים פתוחים ל"${esc(q)}"${cty ? ` ב-${cty}` : ""}, גם אחרי חיפוש בניסוחים דומים.` : `No open tenders for "${esc(q)}"${cty ? ` in ${cty}` : ""}, also after related wordings.`, rows };
  const head = he ? `<b>${res.rows.length} מכרזים פתוחים</b> · "${esc(q)}"${cty ? ` · ${cty}` : ""}` : `<b>${res.rows.length} open tenders</b> · "${esc(q)}"${cty ? ` · ${cty}` : ""}`;
  return { text: `${head}\n\n${rows.map((r, i) => tenderLine(r, i + 1, he)).join("\n\n")}`, rows };
}
// for the AI: the same facts as plain lines, with the id so it can ask for details
async function tenders(q: string, cty: string, n = 6): Promise<string> {
  const res = await searchTendersSmart(q, cty); const rows = res.rows.slice(0, n);
  if (!rows.length) return `0 open tenders (searched: ${q}${cty ? ", " + cty : ""}; matched: ${res.how})`;
  return `${res.rows.length} open tenders (matched: ${res.how})\n` + rows.map((r) => `- id ${r.id} | ${r.title_en || r.title} | ${r.buyer} | ${r.country} | ${money(num(r.est_value_usd))} | deadline ${r.deadline} | fit ${r.fit || r.score} | open: ${r.id ? tenderUrl(r.id) : ""}`).join("\n");
}
function tenderDetail(r: Row, he: boolean): string {
  const L = (h: string, e: string, v: string) => (v ? `${he ? h : e}: ${v}\n` : "");
  const routes = routeOptions({ country: r.country, access: r.access, title: r.title_en, sector: r.sector, value_usd: num(r.est_value_usd), stage: r.stage } as never);
  const best = routes.find((x) => x.verdict === "supported") || routes.find((x) => x.verdict === "conditional");
  const title = esc(r.title_en || r.title || "");
  return `<b>${r.id ? a(tenderUrl(r.id), title) : title}</b>\n${esc(r.buyer || "")} · ${esc(r.country || "")}\n\n`
    + L("שווי", "Value", money(num(r.est_value_usd))) + L("דדליין", "Deadline", r.deadline ? `${esc(r.deadline)} (${due(r.deadline, he)})` : "")
    + L("התאמה", "Fit", r.fit ? `${esc(r.fit)}${r.fit_why ? ` · ${esc(r.fit_why).slice(0, 140)}` : ""}` : "")
    + L("סיכוי זכייה", "Win chance", pct(r.p_win_market)) + L("מתחרים צפויים", "Expected bidders", esc(r.est_bidders || ""))
    + L("ספק מכהן", "Incumbent", esc(r.incumbent || "")) + L("זכיות של הקונה ב-12 חודשים", "Buyer awards, 12 months", esc(r.buyer_awards_12m || ""))
    + L("שווי צפוי", "Expected value", num(r.ev_usd) < 0 ? (he ? "שלילי (לא משתלם)" : "negative (not worth it)") : money(num(r.ev_usd))) + L("החלטת המנוע", "Engine decision", esc(r.decision || ""))
    + (best ? L("דרך כניסה", "Entry route", `${esc(best.route)} (${esc(best.verdict)}) · ${esc(best.next).slice(0, 160)}`) : "")
    + (r.link ? `\n${a(r.link, he ? "המכרז באתר המקור" : "Notice at the source")}` : "");
}
async function plays(cty: string, n = 6): Promise<string> {
  const rows = toObjects(await getRange("plays")).filter((p) => !cty || p.country === cty).slice(0, n);
  return rows.length ? rows.map((p) => `• <b>${esc(p.kind)}</b> ${p.country ? a(countryUrl(p.country), esc(p.country)) : ""} · ${esc(p.title)}\n  ${esc(p.thesis).slice(0, 220)}\n  ${esc(p.next_step).slice(0, 160)}`).join("\n") : "-";
}
async function suppliers(q: string, n = 6, he = false): Promise<string> {
  const r = await supplierSearch({ text: q, strict: true });
  const rows = toObjects(r.values).filter((y) => y.match !== "incompatible").slice(0, n);
  if (!rows.length) return he ? `לא מצאתי ספקים מוכחים ל"${esc(q)}".` : `No proven suppliers for "${esc(q)}".`;
  return `<b>${r.total} ${he ? "ספקים" : "suppliers"}</b> · "${esc(r.query || q)}"\n\n` + rows.map((s, i) => `<b>${i + 1}. ${a(supplierUrl(s.supplier, s.country), esc(s.supplier))}</b> · ${esc(s.country)} · tier ${esc(s.tier)}${s.match ? ` · ${esc(s.match)}` : ""}\n${esc((s.products || s.supplied || "").slice(0, 110))}${s.website ? `\n${a(/^https?:/.test(s.website) ? s.website : "https://" + s.website, esc(s.website.replace(/^https?:\/\//, "")))}` : ""}`).join("\n\n");
}
// Suppliers for one tender, ranked the way the web panel does it: the tender's sector, customs code, country and
// title words together (a long title never has to match word for word)
async function tenderSuppliers(t: Record<string, string>, n = 6, he = false): Promise<string> {
  const r = await supplierSearch({ sector: t.sector || "", text: `${t.title_en || t.title || ""} ${t.commodity || ""}`.slice(0, 400), country: t.country || "", region: t.region || "", hs: t.hs || "", n: 15 });
  const rows = toObjects(r.values).filter((y) => y.match !== "incompatible").slice(0, n);
  const title = esc((t.title_en || t.title || "").slice(0, 90));
  if (!rows.length) return he ? `לא מצאתי ספקים מתאימים למכרז:\n<i>${title}</i>` : `No matching suppliers for this tender:\n<i>${title}</i>`;
  return `<b>${he ? `${r.total} ספקים למכרז` : `${r.total} suppliers for the tender`}</b>\n<i>${title}</i>\n\n` + rows.map((s, i) => `<b>${i + 1}. ${a(supplierUrl(s.supplier, s.country), esc(s.supplier))}</b> · ${esc(s.country)} · tier ${esc(s.tier)}${s.match ? ` · ${esc(s.match)}` : ""}\n${esc((s.products || s.supplied || "").slice(0, 110))}${s.website ? `\n${a(/^https?:/.test(s.website) ? s.website : "https://" + s.website, esc(s.website.replace(/^https?:\/\//, "")))}` : ""}`).join("\n\n");
}
async function lastTender(chatId: string): Promise<string> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${MEM}'!A2:C6000`]).catch(() => null))?.[0] || [];
  const mine = rows.filter((r) => r && String(r[0]) === chatId && /^tn:/.test(String(r[2] || "")) && Date.now() - Date.parse(String(r[1] || "")) < 24 * 3600e3);
  return String(mine[mine.length - 1]?.[2] || "").slice(3);
}
async function country(c: string): Promise<string> {
  const d = await countryIntel(c);
  return `<b>${a(countryUrl(d.country), esc(d.country))}</b> ${esc(d.region)}\n${d.open} open tenders (${money(d.open_usd)}), ${d.intl} open to foreign bidders, ${d.pursue} Pursue, ${d.planned} planned projects (${money(d.planned_usd)})\n`
    + `Top sectors: ${d.sectors.slice(0, 4).map((s) => `${s.sector} ${s.n}`).join("; ")}\n`
    + (d.plays.length ? `Plays:\n${d.plays.slice(0, 3).map((p) => `• ${esc(p.kind)}: ${esc(p.title)}`).join("\n")}\n` : "")
    + (d.news.length ? `News:\n${d.news.slice(0, 4).map((x) => `• ${esc(x.title)} (${esc(x.domain)})`).join("\n")}` : "");
}

// The AI answer with its markers turned into cards and buttons: [[T:id]] becomes a numbered tender card with a
// Details button; [[Q:question]] becomes a follow-up button (the questions are kept with the exchange, the button
// carries only its number).
async function dress(raw: string, he: boolean) {
  const questions: string[] = []; let n = 0; const ids: string[] = [];
  let text = raw.replace(/\[\[Q:([^\]]{2,80})\]\]\s*/g, (_m, q) => { if (questions.length < 3) questions.push(String(q).trim()); return ""; });
  const parts = text.split(/(\[\[T:[^\]]+\]\])/), orig = [...parts];
  for (let i = 0; i < parts.length; i++) {
    const m = parts[i].match(/^\[\[T:([^\]]+)\]\]$/);
    if (!m) { parts[i] = parts[i].replace(/^[\s:·-]+(?=\S)/, (x) => (i && /\[\[T:/.test(orig[i - 1] || "") ? "\n" : x)); continue; }
    const r = await findTender(m[1].trim()).catch(() => undefined);
    if (!r) { parts[i] = ""; continue; }
    n += 1; ids.push(r.id); parts[i] = tenderLine(r, n, he);
  }
  text = parts.join("").replace(/^[ \t]*[-•]\s*(?=<b>\d+\.)/gm, "").replace(/\n{3,}/g, "\n\n").trim();
  const keyboard: { text: string; callback_data: string }[][] = [];
  for (let i = 0; i < ids.length; i += 4) keyboard.push(ids.slice(i, i + 4).map((id, k) => ({ text: he ? `פרטים ${i + k + 1}` : `Details ${i + k + 1}`, callback_data: cb("tn", id) })));
  questions.forEach((q, i) => keyboard.push([{ text: q.slice(0, 60), callback_data: `qq:${i}` }]));
  return { text, keyboard, questions };
}

// ---- short memory: the last exchanges of a chat (hidden tab 'Telegram Chat': chat_id, at, question, answer) ------
const MEM = "Telegram Chat";
async function remember(chatId: string, q: string, ans: string, questions: string[] = []) {
  await appendRows(MEM, [[chatId, new Date().toISOString(), q.slice(0, 600), ans.replace(/<[^>]+>/g, "").slice(0, 900), JSON.stringify(questions)]]).catch(() => null);
}
async function lastQuestions(chatId: string): Promise<string[]> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${MEM}'!A2:E6000`]).catch(() => null))?.[0] || [];
  const mine = rows.filter((r) => r && String(r[0]) === chatId && !/^tn:/.test(String(r[2] || "")));
  try { return JSON.parse(String(mine[mine.length - 1]?.[4] || "[]")); } catch { return []; }
}
async function recall(chatId: string): Promise<{ role: "user" | "assistant"; content: string }[]> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${MEM}'!A2:D6000`]).catch(() => null))?.[0] || [];
  const mine = rows.filter((r) => r && String(r[0]) === chatId && !/^tn:/.test(String(r[2] || "")));
  const cut = mine.map((r) => r[2]).lastIndexOf("reset");
  const recent = mine.slice(cut + 1).filter((r) => Date.now() - Date.parse(String(r[1] || "")) < 6 * 3600e3).slice(-4);
  return recent.flatMap((r) => [{ role: "user" as const, content: String(r[2] || "") }, { role: "assistant" as const, content: String(r[3] || "") || "-" }]);
}

export async function handle(chatId: string, text: string, _from: string) {
  await ensureCallbacks();
  const all = await links();
  const link = all.find((l) => l.chat_id === chatId);
  const t = text.trim();
  const he = link ? link.lang === "he" : /[֐-׿]/.test(t);
  if (!link) {
    const m = t.match(/^\/start(?:@\w+)?\s*([A-Za-z0-9]{6})?$/) || t.match(/^([A-Za-z0-9]{6})$/);
    if (m && m[1]) return send(chatId, await linkChat(chatId, m[1], he ? "he" : "en"));
    return send(chatId, he ? "שלום. כדי לקשר את הצ'אט למשתמש שלך שלח את הקוד מהמערכת (היום בשבילך > טלגרם, בתחתית העמוד), למשל: /start AB12CD" : "Hello. To link this chat to your account send the code from the panel (Today for you > Telegram, at the bottom), e.g. /start AB12CD");
  }
  const who = { email: link.email, name: link.name };
  const [cmd, ...rest] = t.split(/\s+/);
  const arg = rest.join(" ");
  const iso = (s: string) => (s.match(/\b([A-Z]{3})\b/) || [])[1] || "";
  try {
    if (/^\/help/.test(cmd)) return send(chatId, he ? HELP_HE : HELP_EN);
    if (/^\/mailcheck/.test(cmd)) { const r = await mailCheck(); return send(chatId, r.ok ? (he ? `תיבת המייל מחוברת (${esc(r.host)}). לא נשלח שום מייל בבדיקה.` : `The mailbox signs in (${esc(r.host)}). No mail was sent.`) : (he ? `החיבור לתיבה נכשל (${esc(r.host)}): ${esc(r.error || "")}` : `Mailbox sign-in failed (${esc(r.host)}): ${esc(r.error || "")}`)); }
    if (/^\/retry/.test(cmd)) { const ok = await retryLatest(agentIo, chatId); return send(chatId, ok ? (he ? "ממשיך מהמקום שבו הסוכן נעצר." : "Continuing from where the agent stopped.") : (he ? "אין ריצה שנעצרה בתקלה." : "No run stopped on an error.")); }
    if (/^\/stop/.test(cmd)) { const n = await stopLatest(chatId); return send(chatId, n ? (he ? "הסוכן נעצר." : "Agent stopped.") : (he ? "אין סוכן פעיל." : "No agent running.")); }
    if (/^\/deal/.test(cmd)) {
      if (!arg.trim()) return send(chatId, he ? "כתוב מה לעשות, למשל: /deal תמצא לי 5,000 טון תירס לבן לקניה" : "Write the request, e.g. /deal find 5,000 t of white maize for Kenya");
      await startRun(agentIo, { chat: chatId, email: link.email, name: link.name, lang: link.lang, request: arg });
      return send(chatId, he ? "התחלתי לעבוד על העסקה. אעדכן כאן בכל שלב, ואבקש אישור לפני כל פנייה." : "Started on the deal. I will update you here and ask approval before any message.");
    }
    // an answer to the agent's open question goes back to the agent
    if (!t.startsWith("/")) { const w = await waitingRun(chatId); if (w) { await resume(agentIo, w, t); return send(chatId, he ? "קיבלתי, ממשיך." : "Got it, continuing."); } }
    if (/^\/alerts/.test(cmd)) { await appendRow(TAB, [chatId, link.email, link.name, new Date().toISOString().slice(0, 16), link.lang, /off/i.test(arg) ? "off" : "on"]); return send(chatId, /off/i.test(arg) ? (he ? "התראות כבויות." : "Alerts off.") : (he ? "התראות פועלות." : "Alerts on.")); }
    if (/^\/tenders/.test(cmd)) {
      await logActivity(who, "tg_tenders", arg); await typing(chatId);
      const c = iso(arg.toUpperCase()), q = arg.replace(c, "").trim();
      if (!q) return send(chatId, he ? "כתוב מוצר או תחום, למשל: /tenders data centre DEU" : "Write a product or field, e.g. /tenders data centre DEU");
      const l = await tenderList(q, c, 6, he);
      return sendCard(chatId, l.text, l.rows.length ? [l.rows.slice(0, 3).map((r, i) => ({ text: he ? `פרטים ${i + 1}` : `Details ${i + 1}`, callback_data: cb("tn", r.id) }))] : undefined);
    }
    if (/^\/new/.test(cmd)) { await remember(chatId, "reset", ""); return send(chatId, he ? "התחלנו שיחה חדשה." : "New conversation."); }
    if (/^\/country/.test(cmd)) { const c = iso(arg.toUpperCase()); if (!c) return send(chatId, he ? "קוד מדינה בן 3 אותיות, למשל /country KEN" : "3-letter code, e.g. /country KEN"); await logActivity(who, "tg_country", c); return send(chatId, await country(c)); }
    if (/^\/plays/.test(cmd)) { await logActivity(who, "tg_plays", arg); return send(chatId, await plays(iso(arg.toUpperCase()))); }
    if (/^\/suppliers/.test(cmd)) {
      await logActivity(who, "tg_suppliers", arg); await typing(chatId);
      if (arg) return send(chatId, await suppliers(arg, 6, he));
      // no product named: the tender opened last in this chat, if any
      const tid = await lastTender(chatId), tr = tid ? await findTender(tid) : null;
      if (tr) return send(chatId, await tenderSuppliers(tr, 6, he));
      return send(chatId, he ? "לאיזה מוצר? למשל:\n/suppliers power transformer\nאו לחץ \"ספקים מתאימים\" מתחת למכרז." : "Which product? For example:\n/suppliers power transformer\nor tap \"Matching suppliers\" under a tender.");
    }
    if (/^\/brief/.test(cmd)) { await logActivity(who, "tg_brief", link.lang); const b = (await readBrief(link.lang)) || (await buildBrief(link.lang, link.email)); return send(chatId, b.text ? b.text.replace(/^## (.*)$/gm, "<b>$1</b>").replace(/\n---[\s\S]*$/, "") : (he ? "אין עדיין מקורות להיום." : "No sources collected yet today.")); }
    // free text: the AI picks tools from the same set and phrases the result from their output only; the last few
    // exchanges of this chat come along, so a follow-up ("and in Germany?", "the second one") is understood
    await logActivity(who, "tg_ask", t.slice(0, 200)); await typing(chatId);
    const tools = [
      { name: "search_tenders", description: "Open tenders ranked by deal fit. words: the product or field in English (a few words, no country names); country: ISO3 or empty. Returns ids.", input_schema: { type: "object", properties: { words: { type: "string" }, country: { type: "string" } }, required: ["words"] } },
      { name: "tender_detail", description: "Everything the system knows about one tender id: value, deadline, fit and why, win chance, expected bidders, incumbent, buyer history, expected value, engine decision, entry route.", input_schema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] } },
      { name: "suppliers", description: "Proven suppliers for an English product phrase, best product fit first.", input_schema: { type: "object", properties: { product: { type: "string" } }, required: ["product"] } },
      { name: "supplier_contact", description: "Contact details on record for one supplier (name and ISO3 country as returned by suppliers).", input_schema: { type: "object", properties: { company: { type: "string" }, country: { type: "string" } }, required: ["company"] } },
      { name: "country_intel", description: "Country intelligence summary for an ISO3 country code: open tenders and value, sectors, theses, news.", input_schema: { type: "object", properties: { country: { type: "string" } }, required: ["country"] } },
      { name: "plays", description: "Deal theses (supply the winner, arbitrage gap, pre-tender, news lead, procurement plan), optionally for one ISO3 country.", input_schema: { type: "object", properties: { country: { type: "string" } } } },
      { name: "start_deal_agent", description: "Start the deal agent only when the user asks to build, run or work on a deal end to end (source a product for a buyer, prepare a bid, find suppliers and contact them). request: the user's full request with the context.", input_schema: { type: "object", properties: { request: { type: "string" } }, required: ["request"] } },
    ];
    const sys = `You are Sinder's deal co-pilot on Telegram, talking to a Sinder trader. Answer from the Deal Desk's own data only, through the tools; call several tools at once when that is faster.
How to answer: in ${he ? "simple, plain Hebrew (no jargon, no em-dashes, no emojis)" : "plain English"}; lead with the direct answer in one or two lines, then at most 6 items, then one short recommendation line.
Tenders: write each tender you mention as its own paragraph that starts with the marker [[T:<id>]] (the id from the tools) and then at most one short line in your own words on why it matters or what is unclear. The system turns the marker into a numbered card with the title as a link, buyer, country, value, days left and fit, plus a Details button, so do not repeat those facts.
Suppliers and countries: when a tool row has an "open" link, make the name a link: <a href="that link">name</a>. Use HTML <b> only for names. Write money as $182.9M and dates as 2026-11-23.
Follow-ups: end with two or three follow-up questions the trader is likely to ask next, each on its own line as [[Q:<question, at most 45 characters>]]; they become buttons. Do not write a "next question" line in the text.
Thinking: understand what the trader is after (a market, a deal, a supplier, a price) and pick the tools that answer it; for a market question search tenders and also look at the country or theses when useful; for "is it worth it" read tender_detail. Use the conversation so far for follow-ups ("the second one", "and in Kenya?").
Search: if a search returns nothing, search again before you answer with other wordings: synonyms, UK and US spelling, the product alone without words like construction or supply, related terms (for example data centre, server room, HPC). Say there is nothing only after that, and name what you searched.
Facts: cite figures exactly as the tools returned them; never invent companies, contacts, prices or dates; a directory match is not a verified fact.`;
    type Msg = { role: "user" | "assistant"; content: unknown };
    const past = await recall(chatId);
    const msgs: Msg[] = [...past, { role: "user", content: t.slice(0, 800) }];
    let answer = "";
    const model = process.env.TG_MODEL || process.env.AGENT_MODEL || MODEL;
    for (let turn = 0; turn < 5; turn++) {
      const r = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: anthropicHeaders(),
        body: JSON.stringify({ model, max_tokens: 1400, system: sys, tools, messages: msgs }) });
      const j = await r.json();
      if (!r.ok) throw new Error(String(j?.error?.message || r.status).slice(0, 200));
      const content = j.content || [];
      const uses = content.filter((b: { type: string }) => b.type === "tool_use") as { id: string; name: string; input: Record<string, string> }[];
      answer = content.filter((b: { type: string }) => b.type === "text").map((b: { text: string }) => b.text).join("").trim() || answer;
      if (!uses.length) break;
      msgs.push({ role: "assistant", content });
      if (turn) await typing(chatId);
      const start = uses.find((u) => u.name === "start_deal_agent");
      if (start) {
        await startRun(agentIo, { chat: chatId, email: link.email, name: link.name, lang: link.lang, request: start.input.request || t });
        await remember(chatId, t, "(started the deal agent)");
        return send(chatId, he ? "פתחתי סוכן עסקאות לבקשה הזו. אעדכן כאן בכל שלב, ואבקש אישור לפני כל פנייה." : "I opened a deal agent for this request. I will update you here and ask approval before any message.");
      }
      // the tools of one turn run together
      const results = await Promise.all(uses.map(async (u) => {
        let out = "-";
        try {
          const c3 = (u.input.country || "").toUpperCase().slice(0, 3);
          if (u.name === "search_tenders") out = await tenders(u.input.words || "", c3, 6);
          else if (u.name === "tender_detail") { const x = await findTender(u.input.id || ""); out = x ? tenderDetail(x, he) : "tender not found or closed"; }
          else if (u.name === "country_intel") out = await country(c3);
          else if (u.name === "plays") out = await plays(c3, 5);
          else if (u.name === "suppliers") out = await suppliers(u.input.product || "", 6, he);
          else if (u.name === "supplier_contact") out = JSON.stringify((await lookupContact(u.input.company || "", c3).catch(() => null)) || { note: "no contact on record" });
        } catch (e) { out = "error: " + String(e).slice(0, 120); }
        return { type: "tool_result", tool_use_id: u.id, content: out.replace(/<a href="([^"]+)">([^<]*)<\/a>/g, "$2 (open: $1)").replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").slice(0, 6000) };
      }));
      msgs.push({ role: "user", content: results });
    }
    const out = await dress(answer || (he ? "לא מצאתי." : "Nothing found."), he);
    await remember(chatId, t, out.text, out.questions);
    return sendCard(chatId, out.text, out.keyboard.length ? out.keyboard : undefined);
  } catch (e) {
    return send(chatId, (he ? "שגיאה: " : "Error: ") + esc(String((e as Error).message || e).slice(0, 200)));
  }
}

// Outbound: the daily brief (when built) and high-confidence plays to every linked chat with alerts on.
export async function broadcast(text: string, lang: "he" | "en") {
  for (const l of await links()) if (l.alerts !== "off" && l.lang === lang) await send(l.chat_id, text);
}

