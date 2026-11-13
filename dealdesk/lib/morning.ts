// The morning Telegram message (05:00 UTC, /api/cron/digest), built from the system's own data only, no AI.
// Replaces the old "three deal theses" message, which repeated the same three plays every day in English.
// Sections, each skipped when empty:
//   1. New since yesterday that fit the reader's profile (not sent before), best first, with country, buyer, value, days left
//   2. Closing within 7 days that fit the profile
//   3. Waiting for you: pending approvals and active deals
//   4. One deal thesis of the day, rotated (never the same play twice within 30 days), public bodies skipped
//   5. The size of the base today (open opportunities, countries)
// Once per chat per UTC day: the day's key goes into the profile's 'sent' list, so a second trigger the same day (a
// retry, or a second instance) sends nothing.
import type { Profile } from "./profiles";
import { matches } from "./match";
import { tenders } from "./index";
import { getRange } from "./panel";
import { pipeline } from "./deal";
import { readRanges, ENGINE_SHEET } from "./sheets";

const esc = (v: unknown) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
const money = (n: number | null) => (!n ? "" : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`);
const link = (url: string, text: string) => (/^https?:\/\//.test(url) ? `<a href="${esc(url)}">${esc(text)}</a>` : esc(text));
const short = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
// play entities that are public bodies, not companies one could supply (e.g. a national printing office that "won" awards)
const PUBLIC_BODY = /\b(nacional|national|minist|ministry|ministerio|state|estado|government|gobierno|municipal|municipio|alcald|universi|instituto|institute|agency|agencia|secretar|departamento|department|imprenta|council|county|city of|hospital|polic|army|ej[eé]rcito|fuerza|armada)\b/i;
const KIND_HE: Record<string, string> = {
  "supply the winner": "לספק לזוכה", "arbitrage gap": "פער מחיר", "procurement plan": "תוכנית רכש", "pre-tender approach": "פנייה לפני מכרז", "news lead": "ליד מחדשות",
};

export type Morning = { text: string; sentKeys: string[]; counts: Record<string, number> };

export function dayKey(d = new Date()) { return `tg-morning:${d.toISOString().slice(0, 10)}`; }

export async function morning(p: Profile | null, he: boolean, sent: Set<string>): Promise<Morning | null> {
  const day = dayKey();
  if (sent.has(day)) return null;                       // already sent today to this reader
  const all = await tenders();
  const byId = new Map(all.map((r) => [r.id, r]));
  // OPEN = a deadline today or later (owner, 13 Nov: a notice without a deadline is not counted as open). Countries =
  // distinct ISO 3166 alpha-3 codes on those rows (multi-country rows split; regions and free text are not countries).
  const open = all.filter((r) => r.dd != null && r.dd >= 0);
  const iso = new Set<string>();
  for (const r of open) for (const c of String(r.c || "").split(",")) if (/^[A-Z]{3}$/.test(c.trim())) iso.add(c.trim());
  const counts: Record<string, number> = { open: open.length, countries: iso.size, no_deadline: all.filter((r) => r.dd == null).length };
  const out: string[] = [];
  const keys: string[] = [day];
  const fmtLine = (m: { id: string; t: string; c: string; b: string; v: number | null; dd: number | null; l: string }) => {
    const bits = [m.c, short(m.b || "", 50), money(m.v), m.dd != null ? (he ? `${m.dd} ימים` : `${m.dd} days`) : ""].filter(Boolean).join(" · ");
    return `• ${link(m.l, short(m.t || m.id, 110))}\n   <i>${esc(bits)}</i>`;
  };

  // 1-2. what fits the profile (or, without a profile, the strongest open opportunities)
  const fit = p ? (await matches(p, { mode: "focus", limit: 400 })).items
                : open.slice().sort((a, b) => (b.sc ?? 0) - (a.sc ?? 0)).slice(0, 400).map((r) => ({ id: r.id, t: r.t, c: r.c, b: r.b, v: r.v, dd: r.dd, l: r.l }));
  const fresh = fit.filter((m) => !sent.has(m.id) && (byId.get(m.id)?.n === 1 || !p)).slice(0, 5);
  const fresh2 = fresh.length ? fresh : fit.filter((m) => !sent.has(m.id)).slice(0, 5);      // nothing flagged new: best unsent
  counts.fit = fit.length; counts.fresh = fresh2.length;
  if (fresh2.length) {
    out.push(`<b>${he ? `הזדמנויות חדשות שמתאימות לך (${fresh2.length} מתוך ${fit.length})` : `New opportunities that fit you (${fresh2.length} of ${fit.length})`}</b>\n${fresh2.map(fmtLine).join("\n")}`);
    keys.push(...fresh2.map((m) => m.id));
  }
  const closing = fit.filter((m) => m.dd != null && m.dd >= 0 && m.dd <= 7 && !fresh2.some((f) => f.id === m.id)).slice(0, 3);
  counts.closing = fit.filter((m) => m.dd != null && m.dd >= 0 && m.dd <= 7).length;
  if (closing.length) out.push(`<b>${he ? `נסגרים השבוע (${counts.closing})` : `Closing this week (${counts.closing})`}</b>\n${closing.map(fmtLine).join("\n")}`);

  // 3. waiting for the owner
  const wait: string[] = [];
  try {
    const g = (await readRanges(ENGINE_SHEET, ["'Agent Approvals'!A2:E5000"]).catch(() => null))?.[0] || [];
    const last = new Map<string, string>();
    for (const r of g) if (r && r[0]) last.set(String(r[0]), String(r[4] || ""));
    const pending = [...last.values()].filter((s) => s === "pending" || s === "needs_review").length;
    counts.approvals = pending;
    if (pending) wait.push(he ? `${pending} פניות ממתינות לאישורך` : `${pending} messages waiting for your approval`);
  } catch { /* no approvals tab */ }
  try {
    const deals = await pipeline();
    counts.deals = deals.length;
    if (deals.length) wait.push(he ? `${deals.length} עסקאות פעילות: ${deals.slice(0, 3).map((d) => esc(d.deal_id)).join(", ")}` : `${deals.length} active deals: ${deals.slice(0, 3).map((d) => esc(d.deal_id)).join(", ")}`);
  } catch { /* no deals */ }
  if (wait.length) out.push(`<b>${he ? "ממתין לך" : "Waiting for you"}</b>\n${wait.map((w) => `• ${w}`).join("\n")}`);

  // 4. one thesis, rotated
  try {
    const g = await getRange("plays"); const h = g[0] || [];
    const plays = g.slice(1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ""])) as Record<string, string>);
    const pick = plays.find((x) => !sent.has(`play:${x.kind}:${x.entity || x.title}`.slice(0, 120)) && !(x.kind === "supply the winner" && PUBLIC_BODY.test(x.entity || x.title)));
    if (pick) {
      const label = he ? KIND_HE[pick.kind] || pick.kind : pick.kind;
      out.push(`<b>${he ? "תזת העסקה של היום" : "Deal thesis of the day"}</b> · ${esc(label)} · ${esc(pick.country)}\n${esc(short(pick.title, 140))}\n<i>${esc(short(pick.thesis || "", 260))}</i>${pick.next_step ? `\n${he ? "צעד הבא" : "Next step"}: ${esc(short(pick.next_step, 180))}` : ""}`);
      keys.push(`play:${pick.kind}:${pick.entity || pick.title}`.slice(0, 120));
    }
  } catch { /* plays unavailable */ }

  if (!out.length) return null;
  const date = new Date().toISOString().slice(0, 10).split("-").reverse().join(".");
  const head = he ? `<b>בוקר טוב · ${date}</b>\n${counts.open.toLocaleString("en")} הזדמנויות פתוחות ב-${counts.countries} מדינות וטריטוריות (עם מועד הגשה עתידי)` : `<b>Good morning · ${date}</b>\n${counts.open.toLocaleString("en")} open opportunities (future deadline) in ${counts.countries} countries and territories`;
  const foot = he ? "/brief תדריך מלא · /plays כל התזות" : "/brief full briefing · /plays all theses";
  return { text: [head, ...out, foot].join("\n\n"), sentKeys: keys, counts };
}
