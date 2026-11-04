import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { linkCode } from "@/lib/telegram";

export const dynamic = "force-dynamic";

// The signed-in user's own link code and the bot's name, for the Today > Telegram box.
export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  if (!process.env.TELEGRAM_BOT_TOKEN) return NextResponse.json({ ok: true, enabled: false });
  return NextResponse.json({ ok: true, enabled: true, bot: process.env.TELEGRAM_BOT_USERNAME || "", code: await linkCode(s.email) });
}
