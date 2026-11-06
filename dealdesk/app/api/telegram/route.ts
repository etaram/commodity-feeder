import { NextRequest, NextResponse } from "next/server";
import { handle, agentCallback } from "@/lib/telegram";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// Telegram webhook. Telegram sends X-Telegram-Bot-Api-Secret-Token when the webhook was set with secret_token;
// any other caller is refused. Replies are sent through the Bot API, never in this response.
export async function POST(req: NextRequest) {
  const secret = process.env.TELEGRAM_WEBHOOK_SECRET || "";
  if (!secret || req.headers.get("x-telegram-bot-api-secret-token") !== secret) return NextResponse.json({ ok: false }, { status: 401 });
  const u = await req.json().catch(() => ({}));
  const cq = u.callback_query;
  if (cq && cq.message?.chat && typeof cq.data === "string") {
    try { await agentCallback(String(cq.message.chat.id), cq.data, String(cq.id)); } catch { /* never retry storms */ }
    return NextResponse.json({ ok: true });
  }
  const m = u.message || u.edited_message;
  if (m && m.chat && typeof m.text === "string") {
    try { await handle(String(m.chat.id), m.text, String(m.from?.username || m.from?.first_name || "")); } catch { /* never retry storms */ }
  }
  return NextResponse.json({ ok: true });
}
