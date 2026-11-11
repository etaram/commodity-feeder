import { NextRequest, NextResponse } from "next/server";
import { liveDeps, scoutOn, scoutRound } from "@/lib/scoutrun";
import { logEvent } from "@/lib/log";

// The scouts' round (lib/scoutrun.ts): fresh contract winners and new tenders are scored, the best ones the day's
// limits allow get a deal agent run each, and every decision is written to the tab 'Scout Seen'. The run reports to
// the owner in Telegram; any outgoing message still waits for his approval. Does nothing unless SCOUT=on.
// The scheduler sends "Authorization: Bearer <CRON_SECRET>"; any other caller is refused. ?dry=1 decides and reports
// without recording or starting anything.
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  if (!scoutOn()) return NextResponse.json({ ok: true, scout: "off", started: 0 });
  try {
    const dry = req.nextUrl.searchParams.get("dry") === "1";
    const r = await scoutRound(await liveDeps(), { dry });
    if (!dry && (r.started || r.skipped)) await logEvent("info", "cron-scout", `scout round: ${r.started} started, ${r.skipped} skipped`, r.note.slice(0, 300)).catch(() => {});
    return NextResponse.json(r);
  } catch (e) {
    await logEvent("error", "cron-scout", "scout round failed", String(e).slice(0, 300)).catch(() => {});
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
