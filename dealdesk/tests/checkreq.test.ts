// Check-now request helpers (lib/checkreq.ts). Run: npm test
import { answers, checkedParts, cleanWebsite } from "@/lib/checkreq";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

ok(cleanWebsite("https://acme.com/about") === "https://acme.com/about", "an https URL is kept");
ok(cleanWebsite("acme.co.il") === "http://acme.co.il" && cleanWebsite(" www.acme.com other") === "http://www.acme.com", "a bare domain gets http://, first token only");
ok(["javascript:alert(1)", "ftp://acme.com", "http://localhost", "acme", "", null, undefined, 42].every((v) => cleanWebsite(v) === ""), "anything else is dropped");
ok(cleanWebsite("https://a.com/" + "x".repeat(400)).length === 300, "capped at 300 characters");
ok(JSON.stringify(checkedParts("2026-11-12")) === JSON.stringify({ checked: "2026-11-12", checked_at: "" }), "hourly row: a date, no time");
ok(JSON.stringify(checkedParts("2026-11-12T12:30:41Z")) === JSON.stringify({ checked: "2026-11-12", checked_at: "2026-11-12T12:30:41Z" }), "check-now row: date and time");
ok(answers("2026-11-12T12:30:41Z", "2026-11-12T12:30:10.000Z") && answers("2026-11-12T12:30:08Z", "2026-11-12T12:30:10.000Z"), "a check after the request (or within 5 s) answers it");
ok(!answers("2026-11-12T12:29:00Z", "2026-11-12T12:30:10.000Z") && !answers("", "2026-11-12T12:30:10.000Z") && !answers("2026-11-12", "x"), "an older check, or none, does not");
if (fail) process.exit(1);
