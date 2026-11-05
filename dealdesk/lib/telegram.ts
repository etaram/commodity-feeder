import { anthropicHeaders } from "@/lib/anthropic";
import { appendRow, ENGINE_SHEET, readRanges } from "./sheets";
import { listUsers } from "./users";
import { searchTenders, supplierSearch, getRange } from "./panel";
import { countryIntel } from "./country";
import { readBrief, buildBrief } from "./brief";
import { claude } from "./anthropic";
import { logActivity } from "./activity";
import { tgEnv } from "./tgenv";

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

export async function links(): Promise<Link[]> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:F2000`]).catch(() => null))?.[0] || [];
  const m = new Map<string, Link>();
  for (const r of rows) if (r && r[0]) m.set(String(r[0]), { chat_id: String(r[0]), email: r[1] || "", name: r[2] || "", lang: r[4] === "en" ? "en" : "he", alerts: r[5] || "on" });
  return [...m.values()];
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
או פשוט לכתוב שאלה.`;
const HELP_EN = `Commands:
/tenders <words> [ISO3] - open tenders by fit
/country <ISO3> - country intelligence
/plays [ISO3] - deal theses
/suppliers <product> - proven suppliers
/brief - today's world brief
/alerts on|off
Or just write a question.`;

type Row = Record<string, string>;
const toObjects = (g: string[][]): Row[] => { const h = g[0] || []; return g.slice(1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ""]))); };

async function tenders(q: string, cty: string, n = 6): Promise<string> {
  const v = [[q, "", cty], ["", "", ""], ["", "", ""], ["", "", ""], ["", "", ""]];
  const rows = toObjects(await searchTenders(v)).slice(0, n);
  if (!rows.length) return "-";
  return rows.map((r) => `• <b>${esc(r.title_en || r.title || "")}</b>\n  ${esc(r.buyer || "")} · ${esc(r.country)} · ${money(Number(String(r.est_value_usd || "").replace(/[^0-9.]/g, "")))} · ${esc(r.deadline || "")} · fit ${esc(r.fit || r.score || "")}${r.link ? `\n  ${esc(r.link)}` : ""}`).join("\n");
}
async function plays(cty: string, n = 6): Promise<string> {
  const rows = toObjects(await getRange("plays")).filter((p) => !cty || p.country === cty).slice(0, n);
  return rows.length ? rows.map((p) => `• <b>${esc(p.kind)}</b> ${esc(p.country)} · ${esc(p.title)}\n  ${esc(p.thesis).slice(0, 220)}\n  ${esc(p.next_step).slice(0, 160)}`).join("\n") : "-";
}
async function suppliers(q: string, n = 6): Promise<string> {
  const r = await supplierSearch({ text: q, strict: true });
  const rows = toObjects(r.values).slice(0, n);
  return rows.length ? `${r.total} proven suppliers\n` + rows.map((s) => `• <b>${esc(s.supplier)}</b> (${esc(s.country)}, tier ${esc(s.tier)}) ${esc((s.products || s.supplied || "").slice(0, 100))}${s.website ? `\n  ${esc(s.website)}` : ""}`).join("\n") : "-";
}
async function country(c: string): Promise<string> {
  const d = await countryIntel(c);
  return `<b>${esc(d.country)}</b> ${esc(d.region)}\n${d.open} open tenders (${money(d.open_usd)}), ${d.intl} open to foreign bidders, ${d.pursue} Pursue, ${d.planned} planned projects (${money(d.planned_usd)})\n`
    + `Top sectors: ${d.sectors.slice(0, 4).map((s) => `${s.sector} ${s.n}`).join("; ")}\n`
    + (d.plays.length ? `Plays:\n${d.plays.slice(0, 3).map((p) => `• ${esc(p.kind)}: ${esc(p.title)}`).join("\n")}\n` : "")
    + (d.news.length ? `News:\n${d.news.slice(0, 4).map((x) => `• ${esc(x.title)} (${esc(x.domain)})`).join("\n")}` : "");
}

export async function handle(chatId: string, text: string, _from: string) {
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
    if (/^\/alerts/.test(cmd)) { await appendRow(TAB, [chatId, link.email, link.name, new Date().toISOString().slice(0, 16), link.lang, /off/i.test(arg) ? "off" : "on"]); return send(chatId, /off/i.test(arg) ? (he ? "התראות כבויות." : "Alerts off.") : (he ? "התראות פועלות." : "Alerts on.")); }
    if (/^\/tenders/.test(cmd)) { await logActivity(who, "tg_tenders", arg); const c = iso(arg.toUpperCase()); return send(chatId, await tenders(arg.replace(c, "").trim(), c)); }
    if (/^\/country/.test(cmd)) { const c = iso(arg.toUpperCase()); if (!c) return send(chatId, he ? "קוד מדינה בן 3 אותיות, למשל /country KEN" : "3-letter code, e.g. /country KEN"); await logActivity(who, "tg_country", c); return send(chatId, await country(c)); }
    if (/^\/plays/.test(cmd)) { await logActivity(who, "tg_plays", arg); return send(chatId, await plays(iso(arg.toUpperCase()))); }
    if (/^\/suppliers/.test(cmd)) { await logActivity(who, "tg_suppliers", arg); return send(chatId, await suppliers(arg)); }
    if (/^\/brief/.test(cmd)) { await logActivity(who, "tg_brief", link.lang); const b = (await readBrief(link.lang)) || (await buildBrief(link.lang, link.email)); return send(chatId, b.text ? b.text.replace(/^## (.*)$/gm, "<b>$1</b>").replace(/\n---[\s\S]*$/, "") : (he ? "אין עדיין מקורות להיום." : "No sources collected yet today.")); }
    // free text: the AI picks tools from the same set and phrases the result from their output only
    await logActivity(who, "tg_ask", t.slice(0, 200));
    const tools = [
      { name: "search_tenders", description: "Open tenders ranked by deal fit. words: English product words; country: ISO3 or empty.", input_schema: { type: "object", properties: { words: { type: "string" }, country: { type: "string" } }, required: ["words"] } },
      { name: "country_intel", description: "Country intelligence summary for an ISO3 country code.", input_schema: { type: "object", properties: { country: { type: "string" } }, required: ["country"] } },
      { name: "plays", description: "Deal theses (supply the winner, arbitrage gap, pre-tender, news lead, procurement plan), optionally for one ISO3 country.", input_schema: { type: "object", properties: { country: { type: "string" } } } },
      { name: "suppliers", description: "Proven suppliers for an English product phrase.", input_schema: { type: "object", properties: { product: { type: "string" } }, required: ["product"] } },
    ];
    const sys = `You answer a Sinder analyst on Telegram from the Deal Desk's own data only, through the tools. Call one or two tools, then answer in ${he ? "Hebrew" : "English"} in at most 12 lines, plain text with HTML <b> for names only, citing figures exactly as the tools returned them. If the tools return nothing, say so. Never invent companies, prices or dates.`;
    type Msg = { role: "user" | "assistant"; content: unknown };
    const msgs: Msg[] = [{ role: "user", content: t.slice(0, 500) }];
    let answer = "";
    for (let turn = 0; turn < 3; turn++) {
      const r = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: anthropicHeaders(),
        body: JSON.stringify({ model: process.env.ANTHROPIC_MODEL || "claude-haiku-5-5", max_tokens: 1200, system: sys, tools, messages: msgs }) });
      const j = await r.json();
      if (!r.ok) throw new Error(String(j?.error?.message || r.status).slice(0, 200));
      const content = j.content || [];
      const uses = content.filter((b: { type: string }) => b.type === "tool_use");
      answer = content.filter((b: { type: string }) => b.type === "text").map((b: { text: string }) => b.text).join("").trim() || answer;
      if (!uses.length) break;
      msgs.push({ role: "assistant", content });
      const results = [];
      for (const u of uses as { id: string; name: string; input: Record<string, string> }[]) {
        let out = "-";
        try {
          if (u.name === "search_tenders") out = await tenders(u.input.words || "", (u.input.country || "").toUpperCase().slice(0, 3), 5);
          else if (u.name === "country_intel") out = await country((u.input.country || "").toUpperCase().slice(0, 3));
          else if (u.name === "plays") out = await plays((u.input.country || "").toUpperCase().slice(0, 3), 5);
          else if (u.name === "suppliers") out = await suppliers(u.input.product || "", 5);
        } catch (e) { out = "error: " + String(e).slice(0, 120); }
        results.push({ type: "tool_result", tool_use_id: u.id, content: out.replace(/<[^>]+>/g, "") });
      }
      msgs.push({ role: "user", content: results });
    }
    return send(chatId, answer || (he ? "לא מצאתי." : "Nothing found."));
  } catch (e) {
    return send(chatId, (he ? "שגיאה: " : "Error: ") + esc(String((e as Error).message || e).slice(0, 200)));
  }
}

// Outbound: the daily brief (when built) and high-confidence plays to every linked chat with alerts on.
export async function broadcast(text: string, lang: "he" | "en") {
  for (const l of await links()) if (l.alerts !== "off" && l.lang === lang) await send(l.chat_id, text);
}

