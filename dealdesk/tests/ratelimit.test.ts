// Sign-in attempt limiter (acceptance F18): the pure limiter with an injected clock, then the login route itself with
// fixture credentials. No Sheets, no network: without a Sheets configuration only the shared team login can succeed.
// Run: npx --yes esbuild@0.24.0 tests/ratelimit.test.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=<out>.js && node <out>.js
process.env.TEAM_USER = "owner@example.com";
process.env.TEAM_PASSCODE = "fixture-passcode-not-a-secret";
delete process.env.GOOGLE_SERVICE_ACCOUNT_JSON; delete process.env.GOOGLE_SHEETS_ID; delete process.env.ENGINE_SHEET_ID;

import { createLimiter, loginKeys, loginLimiter, LOGIN_MAX_FAILS, LOGIN_WINDOW_MS } from "@/lib/ratelimit";
import { POST } from "@/app/api/login/route";
import { sheetsEnabled } from "@/lib/sheets";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const M = 60e3;

async function main() {
  // ---- pure limiter ----
  {
    const l = createLimiter(8, 15 * M);
    let t = 1_000_000;
    let reached = false;
    for (let i = 0; i < 7; i++) reached = l.fail("ip:1.2.3.4", t + i * 1000) || reached;
    ok(l.retryAfter("ip:1.2.3.4", t + 7000) === 0 && !reached, "7 failures: not blocked yet");
    ok(l.fail("ip:1.2.3.4", t + 8000) === true, "the 8th failure reports that the limit is reached");
    ok(l.retryAfter("ip:1.2.3.4", t + 9000) > 0, "8 failures inside the window: blocked");
    ok(l.retryAfter("ip:1.2.3.4", t + 9000) === Math.ceil((t + 15 * M - (t + 9000)) / 1000), "retry-after counts down to when the oldest failure leaves the window");
    ok(l.retryAfter("ip:5.6.7.8", t + 9000) === 0 && l.retryAfter("email:a@example.com", t + 9000) === 0, "other keys are not affected");
    ok(l.noteBlocked("ip:1.2.3.4", t + 9000) === true && l.noteBlocked("ip:1.2.3.4", t + 9500) === false, "a blocked key is noted once per block (one log row, not one per request)");
    ok(l.noteBlocked("ip:5.6.7.8", t + 9000) === false, "a key that is not blocked is never noted");
    ok(l.retryAfter("ip:1.2.3.4", t + 15 * M - 1) > 0, "still blocked just before the window ends");
    ok(l.retryAfter("ip:1.2.3.4", t + 15 * M + 1) === 0, "free again when the oldest failure ages out (sliding window)");
    ok(l.fail("ip:1.2.3.4", t + 15 * M + 2) === true && l.retryAfter("ip:1.2.3.4", t + 15 * M + 3) > 0, "one more failure while 7 are still in the window blocks again");
    ok(l.noteBlocked("ip:1.2.3.4", t + 15 * M + 3) === true, "a new block is noted again");
    t += 60 * M;
    ok(l.retryAfter("ip:1.2.3.4", t) === 0 && l.size() === 0, "expired keys are forgotten");
    for (let i = 0; i < 8; i++) l.fail("email:b@example.com", t + i);
    ok(l.retryAfter("email:b@example.com", t + 10) > 0, "blocked before clear");
    l.clear("email:b@example.com");
    ok(l.retryAfter("email:b@example.com", t + 10) === 0 && l.size() === 0, "clear (successful sign-in) resets the counter");
    for (let i = 0; i < 50; i++) l.fail("email:c@example.com", t + i);
    ok(l.retryAfter("email:c@example.com", t + 60) <= 15 * 60, "many failures never push retry-after beyond one window");
    const small = createLimiter(3, 15 * M, 5);
    for (let i = 0; i < 3; i++) small.fail("ip:victim", t + i);
    for (let i = 0; i < 40; i++) small.fail(`ip:flood-${i}`, t + 10 + i);
    ok(small.size() <= 5, "the table is bounded (a flood of keys cannot grow it without limit)");
    const k = loginKeys(" 9.9.9.9", "  Owner@Example.COM ");
    ok(k.email === "email:owner@example.com" && k.ip.startsWith("ip:"), "e-mail keys are case and whitespace insensitive");
    ok(loginKeys("", "x").ip === "ip:?" && loginKeys("1.1.1.1", "x".repeat(5000)).email.length <= 210, "missing IP shares one bucket; oversized e-mail keys are cut");
    ok(LOGIN_MAX_FAILS === 8 && LOGIN_WINDOW_MS === 15 * M, "sign-in policy: 8 failed attempts per 15 minutes");
  }

  // ---- the login route ----
  ok(!sheetsEnabled(), "fixture: Sheets is not configured in this test (no network, no real users)");
  const call = async (ip: string, email: string, passcode: string) => {
    const req = { json: async () => ({ email, passcode }), headers: new Headers({ "x-forwarded-for": `${ip}, 10.0.0.1` }) };
    const r = await POST(req as never);
    return { status: r.status, body: (await r.json()) as Record<string, unknown>, retry: r.headers.get("retry-after"), cookie: r.headers.get("set-cookie") || "" };
  };
  const GOOD = process.env.TEAM_PASSCODE!, WRONG = "x".repeat(GOOD.length);
  {
    const a = await call("203.0.113.1", "owner@example.com", GOOD);
    ok(a.status === 200 && a.body.ok === true && a.cookie.includes("dd_session="), "the shared team login still signs in (owner access kept)");
  }
  {
    // per IP: one address guessing at many different e-mails
    let codes: number[] = [];
    for (let i = 0; i < 8; i++) codes.push((await call("203.0.113.2", `user${i}@example.com`, WRONG)).status);
    ok(codes.every((c) => c === 401), "the first 8 wrong attempts from one IP get 401");
    const b = await call("203.0.113.2", "user99@example.com", WRONG);
    ok(b.status === 429 && b.body.code === "rate_limited" && /Too many failed sign-in attempts/.test(String(b.body.error)) && Number(b.retry) > 0, "the 9th from that IP gets 429 with a clear message and Retry-After");
    const c = await call("203.0.113.2", "owner@example.com", GOOD);
    ok(c.status === 429 && !c.cookie, "a blocked IP is refused even with the right team passcode (no further guesses, right or wrong)");
    const d = await call("203.0.113.3", "owner@example.com", GOOD);
    ok(d.status === 200, "another IP is not affected by that block");
  }
  {
    // per e-mail: many addresses guessing at the shared team login
    loginLimiter.clear(loginKeys("", "owner@example.com").email);
    for (let i = 0; i < 8; i++) await call(`198.51.100.${i}`, "Owner@Example.com", WRONG);
    const e = await call("198.51.100.200", "owner@example.com", GOOD);
    ok(e.status === 429 && !e.cookie, "the shared team login is rate limited per e-mail across IPs (case insensitive)");
    const f = await call("198.51.100.201", "someone-else@example.com", WRONG);
    ok(f.status === 401, "another e-mail from a fresh IP is not blocked");
  }
  {
    // a success clears the e-mail counter
    const em = loginKeys("", "owner@example.com").email;
    loginLimiter.clear(em);
    for (let i = 0; i < 7; i++) await call(`192.0.2.${i}`, "owner@example.com", WRONG);
    const g = await call("192.0.2.100", "owner@example.com", GOOD);
    ok(g.status === 200, "7 failures then the right passcode: signed in");
    let codes: number[] = [];
    for (let i = 0; i < 7; i++) codes.push((await call(`192.0.2.${110 + i}`, "owner@example.com", WRONG)).status);
    ok(codes.every((c) => c === 401) && (await call("192.0.2.120", "owner@example.com", GOOD)).status === 200, "the successful sign-in cleared the e-mail counter (7 more failures do not block)");
  }
  {
    const h = await call("192.0.2.200", "", "");
    ok(h.status === 401 && loginLimiter.retryAfter(loginKeys("192.0.2.200", "").ip) === 0, "an empty request is refused as before");
  }
  process.exit(fail ? 1 : 0);
}
main().catch((e) => { console.error("FAIL (exception)", e); process.exit(1); });
