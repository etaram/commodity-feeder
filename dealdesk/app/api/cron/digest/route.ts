import { NextRequest, NextResponse } from "next/server";
import { allProfiles, saveProfile } from "@/lib/profiles";
import { listUsers } from "@/lib/users";
import { matches } from "@/lib/match";
import { logEvent } from "@/lib/log";
import { logActivity } from "@/lib/activity";

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
    if (!fresh.length) { report.push({ email, items: 0, sent: false }); continue; }
    const he = p.lang !== "en";
    const rows = fresh.map((r) => `<tr><td style="padding:8px 10px;font-weight:700;color:#0B7A4B;vertical-align:top">${r.score}</td><td style="padding:8px 10px"><a href="${esc(r.l)}" style="color:#1E3A5F;font-weight:600;text-decoration:none">${esc(r.t.slice(0, 160))}</a><div style="color:#667385;font-size:13px">${esc([r.b, r.c, r.dd != null ? (he ? `${r.dd} ימים` : `${r.dd} days`) : "", money(r.v)].filter(Boolean).join(" · "))}</div><div style="color:#667385;font-size:12.5px">${esc(r.why.join(" · "))}</div></td></tr>`).join("");
    const html = `<div dir="${he ? "rtl" : "ltr"}" style="font-family:Arial,sans-serif;font-size:14px;color:#1C2733;max-width:680px">
<p style="font-size:16px;font-weight:700">${he ? `${fresh.length} התאמות חדשות בשבילך` : `${fresh.length} new matches for you`}</p>
<table style="border-collapse:collapse;width:100%">${rows}</table>
<p><a href="${origin}/#forme">${he ? "לכל ההתאמות והגדרות הפרופיל" : "All matches and profile settings"}</a></p>
<p style="color:#667385;font-size:12px">${he ? "מקבל את המייל כי הגדרת תקציר בפרופיל. אפשר לכבות אותו שם." : "You get this because your profile asks for a digest. Turn it off there."}</p></div>`;
    if (dry || !key) { report.push({ email, items: fresh.length, sent: false, error: key ? "dry run" : "no RESEND_API_KEY" }); continue; }
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from, to: [to], subject: he ? `Deal Desk: ${fresh.length} התאמות חדשות` : `Deal Desk: ${fresh.length} new matches`, html }),
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
