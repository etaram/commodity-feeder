import { NextRequest, NextResponse } from "next/server";
import { routeDeps, outreachEnabled } from "@/lib/outreach";
import { tick } from "@/lib/outreach/outbox";
import { logEvent } from "@/lib/log";

// Outreach outbox tick. Disabled unless OUTREACH_ENABLED=1. Even when enabled, the only transport is the test
// transport, which records what would be sent and delivers nothing. Vercel sends "Authorization: Bearer <CRON_SECRET>".
export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  if (!outreachEnabled()) return NextResponse.json({ ok: true, enabled: false });
  try {
    const r = await tick(routeDeps(), { enabled: true, limit: 10 });
    const sent = r.results.filter((x) => x.action === "sent").length;
    if (r.results.length) void logEvent("info", "outreach", `tick: ${r.results.length} processed, ${sent} recorded by the test transport`);
    return NextResponse.json({ ok: true, ...r });
  } catch (e) {
    void logEvent("error", "outreach", String(e).slice(0, 300));
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
