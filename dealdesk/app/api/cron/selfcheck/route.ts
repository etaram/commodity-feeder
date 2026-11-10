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
  const res = await scenarios(`https://${req.headers.get("host")}`, await selfKey(), 0, 40);
  const bad = res.filter((r) => !r.pass);
  // price sources that stopped updating (data/leads/origin_prices_health.json, written by the price run): logged every
  // day, sent with a failure or once a week (Monday), so a dead source is known without a daily nag
  const stale: string[] = await fetch("https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/leads/origin_prices_health.json", { cache: "no-store", signal: AbortSignal.timeout(8000) })
    .then((r) => r.json()).then((j) => Object.entries((j.sources || {}) as Record<string, { status: string; newest_date: string }>).filter(([, v]) => v.status === "stale").map(([k, v]) => `${k} (last ${v.newest_date || "never"})`)).catch(() => []);
  if (stale.length) await logEvent("warn", "prices", `${stale.length} price sources are stale`, stale.join(", ").slice(0, 500)).catch(() => {});
  const weekly = new Date().getUTCDay() === 1 && stale.length > 0;
  await logEvent(bad.length ? "error" : "info", "selfcheck", `${res.length - bad.length} of ${res.length} scenarios passed`, bad.map((b) => `${b.id} ${b.name}: ${b.fails.join("; ")}`).join(" | ").slice(0, 700)).catch(() => {});
  if ((bad.length || weekly) && req.nextUrl.searchParams.get("quiet") !== "1") {
    const text = ((bad.length ? `Deal Desk self-check: ${bad.length} of ${res.length} scenarios failed\n` + bad.map((b) => `- ${b.name}: ${b.fails[0]}`).join("\n") : `Deal Desk self-check: all ${res.length} scenarios passed`)
      + (stale.length ? `\nPrice sources not updating: ${stale.join(", ")}` : "")).slice(0, 1800);
    for (const l of await links().catch(() => [])) if (l.alerts !== "off" && (await findUser(l.email).catch(() => undefined))?.role === "admin") await send(l.chat_id, text).catch(() => {});
  }
  return NextResponse.json({ ok: !bad.length, passed: res.length - bad.length, of: res.length, stale_prices: stale, results: res });
}
