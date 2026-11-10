import { NextRequest, NextResponse } from "next/server";
import { scenarios } from "@/lib/scenarios";
import { selfKey } from "@/lib/selfkey";
import { logEvent } from "@/lib/log";
import { links, send } from "@/lib/telegram";
import { findUser } from "@/lib/users";

// Daily self-check (Vercel Cron, 06:50 UTC): the 20 deal scenarios run against the live app, read-only. The result
// is written to the App Log; when a scenario fails, the admins linked on Telegram get its name and reason, so a
// break between two parts of the system is known the same morning instead of when someone trips on it.
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  const res = await scenarios(`https://${req.headers.get("host")}`, await selfKey(), 0, 20);
  const bad = res.filter((r) => !r.pass);
  await logEvent(bad.length ? "error" : "info", "selfcheck", `${res.length - bad.length} of ${res.length} scenarios passed`, bad.map((b) => `${b.id} ${b.name}: ${b.fails.join("; ")}`).join(" | ").slice(0, 700)).catch(() => {});
  if (bad.length && req.nextUrl.searchParams.get("quiet") !== "1") {
    const text = `Deal Desk self-check: ${bad.length} of ${res.length} scenarios failed\n` + bad.map((b) => `- ${b.name}: ${b.fails[0]}`).join("\n").slice(0, 1500);
    for (const l of await links().catch(() => [])) if (l.alerts !== "off" && (await findUser(l.email).catch(() => undefined))?.role === "admin") await send(l.chat_id, text).catch(() => {});
  }
  return NextResponse.json({ ok: !bad.length, passed: res.length - bad.length, of: res.length, results: res });
}
