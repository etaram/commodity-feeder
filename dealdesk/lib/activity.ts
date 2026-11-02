import { appendRow, ENGINE_SHEET, readRanges, sheetsEnabled } from "./sheets";
import type { Session } from "./auth";

// Who did what in the system, for the admin: one row per action in the hidden 'Activity' tab of the engine sheet.
// Columns: A time (Israel), B email, C name, D role, E action, F target, G detail.
// Never stores passwords, tokens or full AI prompts. Logging never fails the request it describes.
export type ActivityRow = { time: string; email: string; name: string; role: string; action: string; target: string; detail: string };
const TAB = "Activity";
const now = () => new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 19);
const cut = (v: unknown, n: number) => String(v ?? "").replace(/[\r\n\t]+/g, " ").slice(0, n);

export async function logActivity(who: Pick<Session, "email"> & Partial<Session>, action: string, target = "", detail = "") {
  if (!sheetsEnabled()) return;
  try {
    await appendRow(TAB, [now(), cut(who.email, 120), cut(who.name, 80), cut(who.role, 12), cut(action, 40), cut(target, 300), cut(detail, 500)]);
  } catch { /* never block the user's action */ }
}

export async function readActivity(email = "", limit = 500): Promise<ActivityRow[]> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:G50000`]).catch(() => null))?.[0] || [];
  const e = email.trim().toLowerCase();
  const out: ActivityRow[] = [];
  for (let i = rows.length - 1; i >= 0 && out.length < limit; i--) {
    const r = rows[i];
    if (!r || !r[0]) continue;
    if (e && String(r[1] || "").toLowerCase() !== e) continue;
    out.push({ time: r[0] || "", email: r[1] || "", name: r[2] || "", role: r[3] || "", action: r[4] || "", target: r[5] || "", detail: r[6] || "" });
  }
  return out;
}

// What interests each user, from the activity rows of the last N days: visits, time, and the top subjects,
// countries, searches, features and sources. "open" details are "title | subject | country | value".
export type UserSummary = {
  email: string; name: string; role: string; lastSeen: string; days: number; events: number; minutes: number;
  topSubjects: [string, number][]; topCountries: [string, number][]; topSearches: [string, number][];
  topTabs: [string, number][]; topFeatures: [string, number][]; topSources: [string, number][]; recentOpens: string[];
};
export async function summary(days = 30): Promise<UserSummary[]> {
  const rows = await readActivity("", 20000);
  const since = new Date(Date.now() - days * 864e5).toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 19);
  const by = new Map<string, { s: UserSummary; d: Set<string>; m: Record<string, Map<string, number>> }>();
  const bump = (m: Map<string, number>, k: string, n = 1) => { if (k) m.set(k, (m.get(k) || 0) + n); };
  for (const r of rows) {
    if (r.time < since || !r.email) continue;
    let u = by.get(r.email);
    if (!u) {
      u = { s: { email: r.email, name: r.name, role: r.role, lastSeen: r.time, days: 0, events: 0, minutes: 0, topSubjects: [], topCountries: [], topSearches: [], topTabs: [], topFeatures: [], topSources: [], recentOpens: [] }, d: new Set(),
        m: { subj: new Map(), ctry: new Map(), srch: new Map(), tab: new Map(), feat: new Map(), src: new Map() } };
      by.set(r.email, u);
    }
    const { s, m } = u;
    s.events++; u.d.add(r.time.slice(0, 10)); if (r.time > s.lastSeen) s.lastSeen = r.time;
    if (r.action === "time") { const sec = Number(r.detail) || 0; s.minutes += sec / 60; if (r.target.startsWith("tab ")) bump(m.tab, r.target.slice(4), sec / 60); }
    else if (r.action === "view" && r.target.startsWith("tab ")) bump(m.tab, r.target.slice(4), 0.01);
    else if (r.action === "open") {
      const [title, subject, country] = r.detail.split(" | ");
      bump(m.subj, subject || ""); bump(m.ctry, country || "");
      if (s.recentOpens.length < 12) s.recentOpens.push(`${r.time.slice(5, 16)} ${title || r.target}`);
    } else if (r.action === "search") bump(m.srch, r.detail.split(": ").slice(1).join(": ").toLowerCase());
    else if (r.action === "click_out") bump(m.src, r.target);
    else if (r.action === "click") bump(m.feat, r.detail.split(": ").slice(1).join(": ") || r.detail);
    else if (/^(research_|queue_|job_|ai_quick|why_trend|decision|pursuit|watch_add|not_relevant|profile_)/.test(r.action)) bump(m.feat, r.action);
  }
  const top = (m: Map<string, number>, n = 6): [string, number][] => [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => [k, Math.round(v * 10) / 10]);
  return [...by.values()].map(({ s, d, m }) => ({ ...s, days: d.size, minutes: Math.round(s.minutes),
    topSubjects: top(m.subj), topCountries: top(m.ctry), topSearches: top(m.srch), topTabs: top(m.tab), topFeatures: top(m.feat), topSources: top(m.src) }))
    .sort((a, b) => b.lastSeen.localeCompare(a.lastSeen));
}
