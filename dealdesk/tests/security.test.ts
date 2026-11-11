// Red team 11 Nov 2026, findings 7, 10 and 12: what the audit session may call, the Telegram link code and its attempt
// limit, and the owner's notification address (environment only). Pure functions, no network.
import { auditMayCall } from "@/lib/auditscope";
import { createLimiter } from "@/lib/ratelimit";
import { LINK_CODE_LEN, LINK_MAX_FAILS, LINK_WINDOW_MS, linkCode, linkLimiter } from "@/lib/telegram";
import { notifyTo } from "@/lib/notify";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
(async () => {
  // ---- finding 7: the audit session reads, it never sends
  for (const [m, p] of [["POST", "/api/panel/sendmail"], ["GET", "/api/panel/sendmail"], ["POST", "/api/outreach/authorize"], ["POST", "/api/outreach/authorize/"], ["POST", "/api/outreach/outbox"], ["POST", "/api/outreach/reply"],
    ["POST", "/api/outreach/control"], ["POST", "/api/outreach/campaign"], ["POST", "/api/agent/step"], ["POST", "/api/agent/decide"], ["POST", "/api/users"], ["DELETE", "/api/users/x@y.z"], ["POST", "/api/telegram/setup"],
    ["GET", "/api/mcp/key"], ["POST", "/api/deal"], ["POST", "/api/deal/docs"], ["PUT", "/api/clients/C1"], ["POST", "/api/panel/run"], ["POST", "/api/panel/append"], ["POST", "/api/panel/admin"], ["POST", "/api/decision"], ["POST", "/api/job"], ["post", "/api/panel/sendmail"]])
    ok(!auditMayCall(m, p), `audit session refused: ${m} ${p}`);
  // what /api/health, the daily scenarios and the UI audit call stays open
  for (const [m, p] of [["POST", "/api/panel/get"], ["POST", "/api/panel/search"], ["POST", "/api/panel/suppliers-for"], ["POST", "/api/panel/know"], ["POST", "/api/panel/finance"], ["POST", "/api/panel/logistics"], ["POST", "/api/panel/contact"],
    ["GET", "/api/outreach/outbox"], ["GET", "/api/outreach/campaign"], ["GET", "/api/outreach/log"], ["GET", "/api/outreach/suppression"], ["GET", "/api/outreach/linkedin"], ["GET", "/api/users"], ["GET", "/api/telegram/code"], ["GET", "/api/telegram/setup"],
    ["GET", "/api/panel/admin"], ["GET", "/api/deal"], ["GET", "/api/clients"], ["GET", "/api/push"], ["GET", "/api/me"], ["GET", "/"], ["GET", "/panel-shim.js"], ["HEAD", "/api/users"], ["GET", "/api/panel/today"], ["GET", "/api/profile"]])
    ok(auditMayCall(m, p), `audit session allowed: ${m} ${p}`);
  ok(auditMayCall("POST", "/api/dealers") && auditMayCall("POST", "/api/usersx"), "the list matches whole path segments, not prefixes of other names");

  // ---- finding 10: a 10-character link code and 5 wrong codes per hour per chat
  process.env.TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || "1:test";
  const c1 = await linkCode("Owner@Example.com"), c2 = await linkCode("owner@example.com"), c3 = await linkCode("other@example.com");
  ok(LINK_CODE_LEN === 10 && c1.length === 10 && /^[0-9A-F]{10}$/.test(c1), "the link code has 10 characters");
  ok(c1 === c2 && c1 !== c3, "the code depends on the e-mail only, whatever its letter case");
  ok(LINK_MAX_FAILS === 5 && LINK_WINDOW_MS === 3600e3, "the limit is 5 wrong codes per hour");
  const l = createLimiter(LINK_MAX_FAILS, LINK_WINDOW_MS), t0 = 1_800_000_000_000;
  for (let i = 0; i < 4; i++) l.fail("tg:1", t0 + i * 1000);
  ok(l.retryAfter("tg:1", t0 + 5000) === 0, "four wrong codes do not block the chat");
  l.fail("tg:1", t0 + 5000);
  ok(l.retryAfter("tg:1", t0 + 6000) > 0 && l.retryAfter("tg:2", t0 + 6000) === 0, "the fifth wrong code blocks that chat and no other");
  ok(l.retryAfter("tg:1", t0 + 3600e3 + 1) === 0, "the chat may try again an hour after the first of the five");
  ok(linkLimiter.retryAfter("tg:never") === 0 && linkLimiter.size() === 0, "the bot's own limiter starts empty");

  // ---- finding 12: the owner's address comes from NOTIFY_EMAIL only
  delete process.env.NOTIFY_EMAIL;
  ok(notifyTo().length === 0, "without NOTIFY_EMAIL there is no built-in address");
  process.env.NOTIFY_EMAIL = "a@example.com, b@example.com;not-an-address";
  ok(notifyTo().join() === "a@example.com,b@example.com", "NOTIFY_EMAIL may hold several addresses; anything else is ignored");
  delete process.env.NOTIFY_EMAIL;
  const fs = await import("node:fs");
  const src = ["lib/notify.ts", "lib/registry.ts", "app/api/cron/digest/route.ts"].map((f) => fs.readFileSync(f, "utf8")).join("\n");
  ok(!/NOTIFY_EMAIL\s*\|\|\s*"[^"]*@/.test(src) && !/@gmail\.com/.test(src), "no address is hardcoded in the three files");
  ok(!/searchParams\.get\("t"\)/.test(fs.readFileSync("app/api/health/route.ts", "utf8")), "/api/health no longer reads the token from the address");
  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})();
