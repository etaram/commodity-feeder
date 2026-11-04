import { NextRequest, NextResponse } from "next/server";
import { buildBrief, buildGeo } from "@/lib/brief";
import { pushAll } from "@/lib/push";
import { logEvent } from "@/lib/log";

// The morning brief agent: every day at 04:30 UTC (06:30 Israel) it reads the day's collected sources and builds the
// shared world brief once, in Hebrew and English, for every user's home page. One AI call per language per day;
// a brief already built today is reused. Vercel sends "Authorization: Bearer <CRON_SECRET>"; any other caller is refused.
export const dynamic = "force-dynamic";
export const maxDuration = 180;

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  const out: Record<string, unknown> = {};
  await Promise.all((["he", "en"] as const).map(async (lg) => {
    try {
      const [b] = await Promise.all([buildBrief(lg, "morning agent"), buildGeo(lg, "morning agent").catch((e) => logEvent("warn", "brief", `geo (${lg}) failed`, String(e).slice(0, 300)))]);
      out[lg] = { items: b.items, cached: b.cached };
      if (!b.cached && process.env.VAPID_PRIVATE_KEY) await pushAll({ title: lg === "he" ? "התקציר העולמי של הבוקר מוכן" : "This morning's world brief is ready", body: String(b.text).replace(/[#*_\n]+/g, " ").slice(0, 150), url: "/#today", tag: "brief" }, lg);
    } catch (e) {
      out[lg] = { error: String(e).slice(0, 160) };
      await logEvent("warn", "brief", `morning brief (${lg}) failed`, String(e).slice(0, 300));
    }
  }));
  return NextResponse.json({ ok: true, ...out });
}
