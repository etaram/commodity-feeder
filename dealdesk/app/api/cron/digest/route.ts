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
  return NextResponse.json({ ok: true, dry, report });
}
