import { NextRequest, NextResponse } from "next/server";
import { morningCheck } from "@/lib/projects";
import { logEvent } from "@/lib/log";

// Morning check of tender projects and tender watches (Vercel Cron, 05:40 UTC). Sends reminders and new tenders
// to the owners' Telegram chats only; nothing goes to suppliers or buyers. ?dry=1 counts what would be sent.
export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  try {
    const dry = req.nextUrl.searchParams.get("dry") === "1";
    const r = await morningCheck(dry);
    // one line in the App Log per real run, so it can be checked later that the morning job really fired (Vercel keeps runtime logs for an hour only)
    if (!dry) await logEvent("info", "cron-projects", "morning check ran", JSON.stringify(r).slice(0, 300)).catch(() => {});
    return NextResponse.json({ ok: true, ...r });
  } catch (e) {
    await logEvent("error", "cron-projects", "morning check failed", String(e).slice(0, 300)).catch(() => {});
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
