import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { tgEnv } from "@/lib/tgenv";

export const dynamic = "force-dynamic";

// Admin only: registers this deployment as the bot's webhook with Telegram, using the token and the webhook secret
// from the environment, so nobody has to handle the secret by hand. GET shows the current state; POST sets it.
const api = (m: string) => `https://api.telegram.org/bot${tgEnv().token}/${m}`;

export async function GET() {
  const { s, res } = await gate("admin");
  if (!s) return res;
  if (!tgEnv().token) return NextResponse.json({ ok: true, enabled: false, step: "set TELEGRAM_BOT_TOKEN in Vercel and redeploy" });
  const [me, hook] = await Promise.all([fetch(api("getMe")).then((r) => r.json()).catch(() => null), fetch(api("getWebhookInfo")).then((r) => r.json()).catch(() => null)]);
  return NextResponse.json({ ok: true, enabled: true, bot: me?.result?.username || "", webhook: hook?.result?.url || "", pending: hook?.result?.pending_update_count ?? null, last_error: hook?.result?.last_error_message || "" });
}

export async function POST(req: NextRequest) {
  const { s, res } = await gate("admin");
  if (!s) return res;
  const token = tgEnv().token, secret = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (!token || !secret) return NextResponse.json({ ok: false, error: "TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET is not set in Vercel" }, { status: 400 });
  const origin = req.nextUrl.origin.includes("vercel.app") ? "https://desk.sinder.pro" : req.nextUrl.origin;
  const r = await fetch(api("setWebhook"), { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ url: `${origin}/api/telegram`, secret_token: secret, allowed_updates: ["message", "edited_message", "callback_query"], drop_pending_updates: true }) });
  const j = await r.json().catch(() => ({}));
  await logActivity(s, "telegram_setup", `${origin}/api/telegram`, j.ok ? "webhook set" : String(j.description || "failed"));
  return NextResponse.json({ ok: !!j.ok, result: j.description || "", url: `${origin}/api/telegram` });
}
