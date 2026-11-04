import { NextRequest, NextResponse } from "next/server";
import { allProfiles, saveProfile } from "@/lib/profiles";
import { listUsers } from "@/lib/users";
import { matches } from "@/lib/match";
import { logEvent } from "@/lib/log";
import { logActivity } from "@/lib/activity";
import { countryIntel } from "@/lib/country";
import { links as tgLinks, send as tgSend } from "@/lib/telegram";
import { getRange } from "@/lib/panel";
import { tgEnv } from "@/lib/tgenv";

// Daily digest (Vercel Cron, 05:00 UTC). For every active user whose profile asks for one: the new matches since the
// last digest (not sent before, not hidden), best first, by email through Resend. No AI. Weekly digests go on Sundays.
// Vercel sends "Authorization: Bearer <CRON_SECRET>"; any other caller is refused. ?dry=1 returns what would be sent.
export const maxDuration = 60;
const esc = (v: string) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
const money = (n: number | null) => (!n ? "" : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : `$${Math.round(n / 1e3)}K`);

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  const dry = req.nextUrl.searchParams.get("dry") === "1";
  const key = process.env.RESEND_API_KEY;
  const from = process.env.NOTIFY_FROM || "Sinder Deal Desk <onboarding@resend.dev>";
  const origin = req.nextUrl.origin.includes("vercel.app") ? "https://desk.sinder.pro" : req.nextUrl.origin;
  const sunday = new Date().getUTCDay() === 0;
  const active = new Map((await listUsers(true)).filter((u) => u.status === "active").map((u) => [u.email, u]));
  const report: { email: string; items: number; sent: boolean; error?: string }[] = [];
  // Telegram: the three strongest deal theses of the day to every linked chat with alerts on (no AI)
  if (!dry && tgEnv().token) {
    try {
      const g = await getRange("plays"); const h = g[0] || [];
      const rows = g.slice(1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ""]))).slice(0, 3);
      if (rows.length) for (const l of await tgLinks()) if (l.alerts !== "off") {
        const he = l.lang === "he";
        await tgSend(l.chat_id, (he ? "<b>תזות העסקה של הבוקר</b>\n" : "<b>This morning's deal theses</b>\n") + rows.map((p) => `• <b>${p.kind}</b> ${p.country} · ${p.title}\n  ${String(p.next_step).slice(0, 160)}`).join("\n") + (he ? "\n/plays לעוד" : "\n/plays for more"));
      }
    } catch (e) { await logEvent("warn", "telegram", "morning plays failed", String(e).slice(0, 200)); }
  }

  // The shared team login has no Users row: its digest goes to the owner's address.
  const team = (process.env.TEAM_USER || "").trim().toLowerCase();
  const owner = (process.env.NOTIFY_EMAIL || "etamar.ramot@gmail.com").split(/[\s,;]+/)[0];
  if (team) active.set(team, { email: team, name: "Sinder", role: "admin" } as never);
  for (const { email, p } of await allProfiles()) {
    const u = active.get(email);
    const to = email === team ? owner : email;
    if (!u || p.digest === "off" || (p.digest === "weekly" && !sunday)) continue;
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
