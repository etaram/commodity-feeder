import Papa from "papaparse";
import { claude } from "@/lib/anthropic";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";

// The daily world brief: one Haiku call a day over the briefing feed (news, geopolitics, commodities, the owner's
// own expert feeds) plus today's plays, written for a cross-border sourcing firm and cached in the hidden tab
// 'Briefs' (date, lang, text, items, by). Every claim in the brief must cite one of the collected links; the
// prompt forbids outside knowledge, so the brief is a reading of the day's sources, not a forecast.
const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/leads";
const TAB = "Briefs";
type Row = Record<string, string>;
const today = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Jerusalem" });

async function csv(name: string): Promise<Row[]> {
  const r = await fetch(`${RAW}/${name}`, { cache: "no-store" });
  if (!r.ok) return [];
  return (Papa.parse<Row>(await r.text(), { header: true, skipEmptyLines: true }).data || []) as Row[];
}

export async function readBrief(lang: string): Promise<{ date: string; text: string; items: number; by: string } | null> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:E2000`]).catch(() => null))?.[0] || [];
  for (let i = rows.length - 1; i >= 0; i--) {
    const r = rows[i];
    if (r && r[0] === today() && r[1] === lang) return { date: r[0], text: r[2] || "", items: Number(r[3]) || 0, by: r[4] || "" };
  }
  return null;
}

export async function buildBrief(lang: "he" | "en", by: string): Promise<{ date: string; text: string; items: number; by: string; cached: boolean }> {
  const cached = await readBrief(lang);
  if (cached) return { ...cached, cached: true };
  const [items, plays] = await Promise.all([csv("briefing_items.csv"), csv("plays.csv")]);
  const d = today();
  const fresh = items.filter((x) => x.date >= new Date(Date.now() - 2 * 86400e3).toISOString().slice(0, 10)).slice(0, 120);
  if (!fresh.length) return { date: d, text: "", items: 0, by, cached: false };
  const src = fresh.map((x, i) => `[${i + 1}] ${x.date} ${x.topic}/${x.region} ${x.countries ? "(" + x.countries + ") " : ""}${x.title} (${x.source}) ${x.url}${x.summary ? " :: " + x.summary.slice(0, 160) : ""}`).join("\n");
  const pl = plays.slice(0, 15).map((p) => `- ${p.kind}: ${p.country} ${p.sector}: ${p.title}`).join("\n");
  const he = lang === "he";
  const system = `You write the daily world brief for Sinder, an Israeli cross-border sourcing and trading firm (commodities, equipment for infrastructure, energy, defence and health; emerging markets; suppliers in China, India and Turkey; roles: principal, agent, partner to EPC contractors).
Rules: use ONLY the numbered sources given. Every sentence that states a fact ends with its source number in brackets, e.g. [12]. No outside knowledge, no forecasts, no invented numbers. If sources conflict, say so. Plain language, short sentences, no emojis, no em-dashes (use hyphens). ${he ? "Write in Hebrew; keep company, place and commodity names in their original Latin spelling." : "Write in English."}
Format (Markdown, headings exactly as given, each section 2-5 bullets, skip a section with nothing):
## ${he ? "גיאופוליטיקה וסחר" : "Geopolitics and trade"}
## ${he ? "שינוע ומטבע" : "Shipping and currencies"}
## ${he ? "סחורות" : "Commodities"}
## ${he ? "אפריקה" : "Africa"}
## ${he ? "המזרח התיכון וצפון אפריקה" : "Middle East and North Africa"}
## ${he ? "אסיה" : "Asia"}
## ${he ? "אמריקה הלטינית" : "Latin America"}
## ${he ? "קונים ופרויקטים חדשים שנראו בחדשות" : "New buyers and projects seen in the news"}
(one line each: company, country, what, source number)
## ${he ? "מה זה אומר לנו" : "What it means for us"}
(3 bullets at most: a concrete action for a sourcing firm, each tied to a source number or to one of the engine's plays below)`;
  const user = `Date: ${d}\n\nSources (last 48 hours):\n${src}\n\nThe engine's current deal theses (for the last section only):\n${pl || "- none"}`;
  const { text } = await claude({ max_tokens: 2500, system, messages: [{ role: "user", content: user }] });
  const links = fresh.map((x, i) => `[${i + 1}] ${x.url}`).join("\n");
  const full = `${text.trim()}\n\n---\n${he ? "מקורות" : "Sources"}:\n${links}`;
  try { await appendRow(TAB, [d, lang, full.slice(0, 45000), fresh.length, by]); } catch { /* the brief still returns */ }
  return { date: d, text: full, items: fresh.length, by, cached: false };
}
