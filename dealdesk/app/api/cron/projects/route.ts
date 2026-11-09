import { NextRequest, NextResponse } from "next/server";
import { morningCheck } from "@/lib/projects";

// Morning check of tender projects and tender watches (Vercel Cron, 05:40 UTC). Sends reminders and new tenders
// to the owners' Telegram chats only; nothing goes to suppliers or buyers. ?dry=1 counts what would be sent.
export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  try {
    return NextResponse.json({ ok: true, ...(await morningCheck(req.nextUrl.searchParams.get("dry") === "1")) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
