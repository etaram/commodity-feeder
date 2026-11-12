// Screen check: what the owner's screens would show, measured from inside the server instance (read-only).
// Runs the app's own self-check (/api/health, every panel route the way the panel calls it, nothing written or sent)
// with the instance's CRON_SECRET, which never leaves the container. Then judges what a person would see:
//   ERROR  a route that fails or returns an error text (the red banner)
//   EMPTY  a screen that must have data and came back with no rows
//   STALE  the screen's own "updated" time is older than its normal refresh interval plus a margin
// Prints names, counts and ages only (the workflow log is public). Exit code 1 when anything is ERROR, EMPTY or STALE.
// Usage: docker exec -i -e BASE=https://... sinder-server-app node - < _screen_check.js
const BASE = process.env.BASE;
const SECRET = process.env.CRON_SECRET || process.env.AUDIT_TOKEN || "";

// screens that must never be empty: [self-check name, minimum rows]
const MUST_HAVE = [
  ["get:tenders", 100], ["get:suppliers", 100], ["get:markets", 5], ["get:meta", 1], ["get:stats", 1], ["get:intel", 1],
  ["get:contacts", 1], ["get:accounts", 1], ["search tenders", 1], ["search suppliers", 1], ["suppliers-for", 1],
  ["today", 0], ["commodities all", 0], ["coverage", 0],
];
// "updated" time per screen: [label, regex over the self-check output summary or first row, max age in hours]
const MAX_AGE_H = { tenders: 6, suppliers: 30, markets: 30, intel: 30, today: 6, meta: 6 };

const ageH = (s) => { const t = Date.parse(s); return Number.isFinite(t) ? (Date.now() - t) / 36e5 : null; };
const findTimes = (o) => {          // ISO-like times anywhere in the check's summary, header or first rows
  const txt = [o.sum, o.head, JSON.stringify(o.sample || [])].join(" ");
  return [...txt.matchAll(/20\d\d-\d\d-\d\d[T ]\d\d:\d\d(:\d\d)?(\.\d+)?Z?/g)].map((m) => m[0].replace(" ", "T") + (m[0].endsWith("Z") ? "" : "Z"));
};

(async () => {
  if (!BASE) { console.log("BASE not given"); process.exit(2); }
  if (SECRET.length < 16) { console.log("ERROR  the instance has no CRON_SECRET, the self-check cannot run"); process.exit(1); }
  const t0 = Date.now();
  let j;
  try {
    const r = await fetch(`${BASE}/api/health?sample=2`, { headers: { authorization: `Bearer ${SECRET}` }, signal: AbortSignal.timeout(280000) });
    j = await r.json();
    if (r.status !== 200) { console.log(`ERROR  self-check answered ${r.status}`); process.exit(1); }
  } catch (e) { console.log(`ERROR  self-check did not answer: ${String(e).slice(0, 120)}`); process.exit(1); }
  const checks = j.checks || [];
  const by = Object.fromEntries(checks.map((c) => [c.name, c]));
  const problems = [];
  for (const c of checks) {
    if (c.status !== 200 || c.err) problems.push(`ERROR  ${c.name}: ${c.status} ${String(c.err || "").replace(/[A-Za-z0-9_-]{32,}/g, "<long>").slice(0, 100)}`);
  }
  for (const [name, min] of MUST_HAVE) {
    const c = by[name];
    if (!c) { problems.push(`ERROR  ${name}: not in the self-check`); continue; }
    if (c.status !== 200 || c.err) continue;     // already counted
    const rows = typeof c.rows === "number" ? c.rows - 1 : null;     // first row is the header
    const listed = /\[(\d+)\]/.exec(c.sum || "");
    const n = rows ?? (listed ? Number(listed[1]) : null);
    if (min > 0 && n !== null && n < min) problems.push(`EMPTY  ${name}: ${n} rows (want at least ${min})`);
  }
  const fresh = [];
  for (const [key, maxH] of Object.entries(MAX_AGE_H)) {
    const c = by[`get:${key}`] || by[key];
    if (!c || c.status !== 200) continue;
    const ages = findTimes(c).map(ageH).filter((a) => a !== null && a > -1);
    if (!ages.length) { fresh.push(`  ${key.padEnd(10)} no time shown`); continue; }
    const newest = Math.min(...ages);
    fresh.push(`  ${key.padEnd(10)} newest ${newest.toFixed(1)} h old (max ${maxH})`);
    if (newest > maxH) problems.push(`STALE  ${key}: newest data ${newest.toFixed(1)} h old, normal is under ${maxH} h`);
  }
  console.log(`self-check: ${checks.length} screens/routes in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  for (const c of checks) console.log(`  ${String(c.status).padEnd(4)} ${String(c.ms).padStart(6)} ms  ${c.name.padEnd(24)} ${typeof c.rows === "number" ? `${c.rows - 1} rows` : ""}`);
  // connections (login only, nothing sent): mail box login, bot token present, webhook host
  const mail = j.mail || {}; const tg = j.telegram;
  console.log(`mail login (no message sent): ${mail.ok ? "OK" : "FAILED " + String(mail.error || "").replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/g, "<email>").slice(0, 120)}`);
  console.log(`telegram bot token: ${j.telegram_token ? "present" : "missing"}; webhook: ${tg && typeof tg === "object" ? `host ${tg.url_host || "(none)"}, last error ${tg.last_error ? "yes" : "none"}` : String(tg || "")}`);
  console.log(`AI key: ${j.ai && j.ai.ok ? "OK" : "FAILED"}`);
  console.log("freshness (time the screen itself shows):"); fresh.forEach((l) => console.log(l));
  console.log(problems.length ? `\nPROBLEMS (${problems.length}):\n${problems.join("\n")}` : "\nOK: every screen answered, none empty, none stale");
  process.exit(problems.length ? 1 : 0);
})();
