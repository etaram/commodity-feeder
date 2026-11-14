import { NextRequest, NextResponse } from "next/server";
import { allProfiles, saveProfile } from "@/lib/profiles";
import { listUsers } from "@/lib/users";
import { matches } from "@/lib/match";
import { logEvent } from "@/lib/log";
import { logActivity } from "@/lib/activity";
import { countryIntel } from "@/lib/country";
import { links as tgLinks, send as tgSend } from "@/lib/telegram";
import { morning } from "@/lib/morning";
import { tgEnv } from "@/lib/tgenv";
import { pushAll } from "@/lib/push";
import { notifyTo } from "@/lib/notify";
import { buildMacro } from "@/lib/brief";

// Daily digest (Vercel Cron, 05:00 UTC). For every active user whose profile asks for one: the new matches since the
// last digest (not sent before, not hidden), best first, by email through Resend. No AI. Weekly digests go on Sundays.
// Vercel sends "Authorization: Bearer <CRON_SECRET>"; any other caller is refused. ?dry=1 returns what would be sent.
export const maxDuration = 60;
const MORNING_SENT = new Map<string, string[]>();   // in-process second guard (same day, same instance)
const esc = (v: string) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
const money = (n: number | null) => (!n ? "" : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : `$${Math.round(n / 1e3)}K`);

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  const dry = req.nextUrl.searchParams.get("dry") === "1";
  // ?preview=morning: the morning message each linked chat would get now, nothing sent or saved (the day key ignored)
  if (req.nextUrl.searchParams.get("preview") === "morning") {
    const profiles = new Map((await allProfiles()).map((x) => [x.email, x.p]));
    const out = [];
    for (const l of (await tgLinks()).slice(0, 5)) {
      const p = profiles.get(l.email) || null;
      const m = await morning(p, l.lang === "he", new Set((p?.sent || []).filter((k) => !k.startsWith("tg-morning:"))));
      out.push({ lang: l.lang, has_profile: Boolean(p), alerts: l.alerts, chars: m?.text.length || 0, counts: m?.counts || null, text: m?.text || "" });
    }
    return NextResponse.json({ ok: true, preview: out });
  }
  const key = process.env.RESEND_API_KEY;
  const from = process.env.NOTIFY_FROM || "Sinder Deal Desk <onboarding@resend.dev>";
  const origin = req.nextUrl.origin.includes("vercel.app") ? "https://desk.sinder.pro" : req.nextUrl.origin;
  const sunday = new Date().getUTCDay() === 0;
  const active = new Map((await listUsers(true)).filter((u) => u.status === "active").map((u) => [u.email, u]));
  const report: { email: string; items: number; sent: boolean; error?: string }[] = [];
  // Telegram: the morning message (lib/morning.ts): what is new and fits each reader, what closes this week, what waits
  // for them, one rotated deal thesis. Once per chat per day (the day's key is kept in the reader's profile), no AI.
  if (!dry && tgEnv().token) {
    try {
      const profiles = new Map((await allProfiles()).map((x) => [x.email, x.p]));
      let pushed = false;
      for (const l of await tgLinks()) if (l.alerts !== "off") {
        const he = l.lang === "he";
        const p = profiles.get(l.email) || null;
        // force=1 (ops task morning-send, used once after a fix): today's day key is ignored, item keys still apply
        const force = req.nextUrl.searchParams.get("force") === "1";
        const sentSet = new Set([...(p?.sent || []), ...(MORNING_SENT.get(l.chat_id) || [])].filter((k) => !(force && k.startsWith("tg-morning:"))));
        const m = await morning(p, he, sentSet);
        if (!m) continue;
        MORNING_SENT.set(l.chat_id, m.sentKeys);
        if (p) { p.sent = [...(p.sent || []), ...m.sentKeys].slice(-3000); await saveProfile(l.email, p).catch(() => {}); }
        await tgSend(l.chat_id, m.text.slice(0, 4000));
        if (!pushed && process.env.VAPID_PRIVATE_KEY) {
          pushed = true;
          for (const lg of ["he", "en"] as const) await pushAll({ title: lg === "he" ? "בוקר טוב" : "Good morning", body: lg === "he" ? `${m.counts.fresh || 0} הזדמנויות חדשות שמתאימות לך, ${m.counts.closing || 0} נסגרות השבוע` : `${m.counts.fresh || 0} new fits, ${m.counts.closing || 0} closing this week`, url: "/#today", tag: "morning" }, lg);
        }
      }
    } catch (e) { await logEvent("warn", "telegram", "morning message failed", String(e).slice(0, 200)); }
  }

  if (req.nextUrl.searchParams.get("only") === "telegram") return NextResponse.json({ ok: true, only: "telegram" });

  // The shared team login has no Users row: its digest goes to the owner's address (NOTIFY_EMAIL; no address is kept
  // in the code, so without it that one digest is skipped and one event is logged).
  const team = (process.env.TEAM_USER || "").trim().toLowerCase();
  const owner = notifyTo()[0] || "";
  if (team) active.set(team, { email: team, name: "Sinder", role: "admin" } as never);
  for (const { email, p } of await allProfiles()) {
    const u = active.get(email);
    const to = email === team ? owner : email;
    if (!u || p.digest === "off" || (p.digest === "weekly" && !sunday)) continue;
    if (!to) { await logEvent("warn", "digest", "NOTIFY_EMAIL is not set: the team login's digest was skipped"); report.push({ email, items: 0, sent: false, error: "NOTIFY_EMAIL is not set" }); continue; }
    const sent = new Set(p.sent || []);
    const m = await matches(p, { mode: "focus", limit: 300 });
    const fresh = m.items.filter((r) => !sent.has(r.id)).slice(0, 12);
    const he = p.lang === "he";
    // Sundays: a country watch for the profile's countries (open tenders, plays, this week's headlines), from the brain's layers
    let watch = "";
    if (sunday && (p.countries || []).length) {
      for (const c of (p.countries || []).slice(0, 6)) {
        try {
          const d = await countryIntel(c);
          watch += `<h3 style="margin:14px 0 4px">${esc(c)} · ${d.open} ${he ? "מכרזים פתוחים" : "open tenders"}, ${d.pursue} Pursue, ${d.planned} ${he ? "פרויקטים בתכנון" : "planned projects"}</h3>`
            + (d.plays.length ? `<ul>${d.plays.slice(0, 3).map((x) => `<li><b>${esc(x.kind)}</b>: ${esc(x.title)}</li>`).join("")}</ul>` : "")
            + (d.news.length ? `<ul>${d.news.slice(0, 5).map((n) => `<li><a href="${esc(n.url)}">${esc(n.title)}</a> <span style="color:#667385">${esc(n.domain)}</span></li>`).join("")}</ul>` : "");
        } catch { /* a country with no data is skipped */ }
      }
    }
    if (!fresh.length && !watch) { report.push({ email, items: 0, sent: false }); continue; }
    const rows = fresh.map((r) => `<tr><td style="padding:8px 10px;font-weight:700;color:#0B7A4B;vertical-align:top">${r.score}</td><td style="padding:8px 10px"><a href="${esc(r.l)}" style="color:#1E3A5F;font-weight:600;text-decoration:none">${esc(r.t.slice(0, 160))}</a><div style="color:#667385;font-size:13px">${esc([r.b, r.c, r.dd != null ? (he ? `${r.dd} ימים` : `${r.dd} days`) : "", money(r.v)].filter(Boolean).join(" · "))}</div><div style="color:#667385;font-size:12.5px">${esc(r.why.join(" · "))}</div></td></tr>`).join("");
    const html = `<div dir="${he ? "rtl" : "ltr"}" style="font-family:Arial,sans-serif;font-size:14px;color:#1C2733;max-width:680px">
${fresh.length ? `<p style="font-size:16px;font-weight:700">${he ? `${fresh.length} התאמות חדשות בשבילך` : `${fresh.length} new matches for you`}</p>` : ""}
<table style="border-collapse:collapse;width:100%">${rows}</table>
${watch ? `<h2 style="font-size:15px;margin-top:18px">${he ? "המדינות במעקב, השבוע" : "Your watched countries this week"}</h2>${watch}<p><a href="${origin}/#country">${he ? "עמוד המדינה" : "Country page"}</a></p>` : ""}
<p><a href="${origin}/#forme">${he ? "לכל ההתאמות והגדרות הפרופיל" : "All matches and profile settings"}</a></p>
<p style="color:#667385;font-size:12px">${he ? "מקבל את המייל כי הגדרת תקציר בפרופיל. אפשר לכבות אותו שם." : "You get this because your profile asks for a digest. Turn it off there."}</p></div>`;
    if (dry || !key) { report.push({ email, items: fresh.length, sent: false, error: key ? "dry run" : "no RESEND_API_KEY" }); continue; }
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from, to: [to], subject: fresh.length ? (he ? `Deal Desk: ${fresh.length} התאמות חדשות` : `Deal Desk: ${fresh.length} new matches`) : (he ? "Deal Desk: המדינות במעקב, השבוע" : "Deal Desk: your watched countries this week"), html }),
    }).catch((e) => ({ ok: false, status: 0, text: async () => String(e) }) as unknown as Response);
    if (!r.ok) {
      const err = (await r.text()).slice(0, 200);
      report.push({ email, items: fresh.length, sent: false, error: err });
      await logEvent("warn", "digest", `digest to ${email} failed ${r.status}`, err, email);
      continue;
    }
    p.sent = [...(p.sent || []), ...fresh.map((x) => x.id)].slice(-3000);
    p.lastDigest = new Date().toISOString().slice(0, 16);
    await saveProfile(email, p);
    await logActivity({ email, name: u.name, role: u.role }, "digest_sent", "", `${fresh.length} items`);
    report.push({ email, items: fresh.length, sent: true });
  }
  // Macro business review (owner, 14 Nov 2026): world economy, commodities, emerging markets and what is scheduled
  // ahead, by e-mail. Profiles choose daily, weekly (Sundays) or off, and the language. The owner gets it daily in
  // Hebrew unless one of the profiles that resolves to the owner's address chose otherwise. On Sundays daily readers get
  // the longer weekly edition. One AI call per language and edition per day, shared by all readers (cached in Briefs).
  const macroReport: { to: string; lang: string; weekly: boolean; sent: boolean; error?: string }[] = [];
  try {
    const want = new Map<string, { lang: "he" | "en"; freq: string }>();
    for (const { email, p } of await allProfiles()) {
      if (!active.has(email) || !p.macro || p.macro === "off") continue;
      const to = email === team ? owner : email;
      if (to) want.set(to, { lang: p.macroLang === "en" ? "en" : "he", freq: p.macro });
    }
    if (owner && !want.has(owner) && process.env.MACRO_OWNER !== "off") want.set(owner, { lang: process.env.MACRO_OWNER_LANG === "en" ? "en" : "he", freq: "daily" });
    const md = (txt: string) => esc(txt).replace(/^## (.*)$/gm, '<h3 style="margin:16px 0 6px;color:#1E3A5F">$1</h3>')
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^[-*] (.*)$/gm, "<li>$1</li>").replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul style="margin:0;padding-inline-start:20px">${m}</ul>`)
      .replace(/^\[(\d+)\] (https?:\S+)$/gm, '<div style="font-size:12px">[$1] <a href="$2">$2</a></div>').replace(/\n{2,}/g, "<br>").replace(/\n/g, " ");
    const built = new Map<string, string>();
    for (const [to, w] of want) {
      const weekly = sunday;
      if (w.freq === "weekly" && !sunday) continue;
      const k = `${w.lang}-${weekly ? "w" : "d"}`;
      if (dry) { macroReport.push({ to, lang: w.lang, weekly, sent: false, error: "dry run" }); continue; }
      if (!built.has(k)) built.set(k, (await buildMacro(w.lang, weekly, "digest")).text || "");
      const txt = built.get(k) || "";
      if (!txt || !key) { macroReport.push({ to, lang: w.lang, weekly, sent: false, error: key ? "empty review" : "no RESEND_API_KEY" }); continue; }
      const he = w.lang === "he";
      const html = `<div dir="${he ? "rtl" : "ltr"}" style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#1C2733;max-width:680px">
<p style="font-size:17px;font-weight:700;margin:0 0 4px">${he ? (weekly ? "הסקירה העסקית השבועית" : "הסקירה העסקית היומית") : (weekly ? "Weekly business review" : "Daily business review")}</p>
<p style="color:#667385;margin:0 0 10px">${new Date().toLocaleDateString(he ? "he-IL" : "en-GB", { timeZone: "Asia/Jerusalem", day: "numeric", month: "long", year: "numeric" })}</p>
${md(txt)}
<p style="color:#667385;font-size:12px;margin-top:16px">${he ? "נכתב אוטומטית מתוך מקורות ברשת שמופיעים למטה; מה שלא סופי מסומן כצפוי. להפסקה או לשינוי תדירות ושפה: הגדרות הפרופיל ב-Deal Desk." : "Written automatically from the web sources listed; anything not final is marked as expected. To stop it or change frequency and language: profile settings in the Deal Desk."} <a href="${origin}/#forme">${he ? "הגדרות" : "Settings"}</a></p></div>`;
      const r = await fetch("https://api.resend.com/emails", {
        method: "POST", headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ from, to: [to], subject: he ? (weekly ? "Sinder: הסקירה העסקית השבועית" : "Sinder: הסקירה העסקית היומית") : (weekly ? "Sinder: weekly business review" : "Sinder: daily business review"), html }),
      }).catch((e) => ({ ok: false, status: 0, text: async () => String(e) }) as unknown as Response);
      if (!r.ok) { const err = (await r.text()).slice(0, 200); macroReport.push({ to, lang: w.lang, weekly, sent: false, error: err }); await logEvent("warn", "digest", `macro review to ${to} failed ${r.status}`, err); continue; }
      macroReport.push({ to, lang: w.lang, weekly, sent: true });
    }
  } catch (e) { await logEvent("warn", "digest", "macro review failed", String(e).slice(0, 200)); }
  return NextResponse.json({ ok: true, dry, report, macro: macroReport.map((x) => ({ ...x, to: x.to.replace(/^(.).*(@.*)$/, "$1***$2") })) });
}
