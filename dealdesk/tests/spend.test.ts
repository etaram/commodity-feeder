// Spending this month (lib/spend.ts): month sums from the ledgers, caps from the environment with safe defaults,
// plain words, unconfirmed fixed costs never added to the total, and the AI monthly cap refusal message.
import { agentMonth, aiMonth, envCap, levelOf, monthKey, parseFixed, spendReport } from "@/lib/spend";
import { capMessage, CAP_REFUSAL } from "@/lib/anthropic";
import FIXED from "@/lib/fixedcosts.json";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

const now = Date.parse("2026-11-12T13:00:00Z");
ok(monthKey(now) === "2026-11", "month key is the UTC calendar month");
const ai = [["time", "job", "ws", "model", "in", "out", "cache", "searches", "usd"],
  ["2026-10-31T23:59:00Z", "brief", "", "m", "1", "1", "0", "0", "9"],
  ["2026-11-01T00:01:00Z", "brief", "", "m", "1", "1", "0", "0", "1.5"],
  ["2026-11-12T10:00:00Z", "deal agent", "", "m", "1", "1", "0", "0", "2.25"],
  ["2026-11-12T10:00:00Z", "bad", "", "m", "1", "1", "0", "0", "not a number"]];
const a = aiMonth(ai, "2026-11");
ok(a.usd === 3.75 && a.calls === 2 && a.byJob.brief === 1.5, "AI ledger: only this month's rows, unreadable amounts skipped");

const led = [["2026-11-12T08:00:00Z", "t1", "reserve", "r", "scout", "0.5"], ["2026-11-12T08:01:00Z", "t1", "settle", "r", "scout", "0.1"],
  ["2026-11-12T09:00:00Z", "t2", "reserve", "r", "scout", "0.4"], ["2026-11-12T09:00:01Z", "t2", "release", "r", "scout", ""],
  ["2026-11-12T10:00:00Z", "t3", "reserve", "r", "scout", "0.3"], ["2026-10-30T10:00:00Z", "t0", "reserve", "r", "scout", "9"]];
const g = agentMonth(led, "2026-11");
ok(Math.abs(g.usd - 0.4) < 1e-9 && g.reservations === 3, "agent ledger: settled = actual, released = 0, open = worst case, other months ignored");

ok(envCap({}, "X", 30) === 30 && envCap({ X: "" }, "X", 30) === 30, "unset cap = the default");
ok(envCap({ X: "12.5" }, "X", 30) === 12.5, "a set cap is used");
ok(envCap({ X: "thirty" }, "X", 30) === 0 && envCap({ X: "-1" }, "X", 30) === 0, "an unreadable cap counts as 0 (refuse), never the default");

ok(levelOf(5, 30).words === "within budget" && levelOf(25, 30).words === "near the cap" && levelOf(30, 30).words === "stopped at the cap", "plain words: within, near (80%), stopped");
ok(levelOf(0, 0).level === "off" && levelOf(null, 30).level === "unknown", "cap 0 with nothing spent = off; unknown spend says so");

const fx = parseFixed(FIXED);
ok(fx.length === 4 && fx.every((f) => f.status === "to confirm" && f.monthly_usd === null), "shipped fixed costs: server, domain, mailbox, phone, all 'to confirm' (no invented prices)");
const fx2 = parseFixed('[{"name":"Server","monthly_usd":20,"status":"confirmed"},{"name":"Domain","monthly_usd":2},{"name":"Phone","monthly_usd":"x","status":"confirmed"}]');
ok(fx2[0].status === "confirmed" && fx2[1].status === "to confirm" && fx2[2].monthly_usd === null && fx2[2].status === "to confirm", "an amount counts only when confirmed; an unreadable amount is 'to confirm'");
ok(parseFixed("not json").length === 0, "unreadable configuration = no fixed lines");

const r = spendReport({ now, env: { ANTHROPIC_MONTHLY_CAP_USD: "4" }, ai: { rows: ai }, agent: { rows: led }, fixed: fx2 });
const an = r.services.find((s) => s.id === "anthropic")!;
ok(an.spent_usd === 3.75 && an.cap_usd === 4 && an.words === "near the cap", "Anthropic line: month so far against its cap");
ok(r.services.find((s) => s.id === "search")!.level === "off" && r.services.find((s) => s.id === "whatsapp")!.spent_usd === 0, "search and WhatsApp: not connected, 0");
ok(r.total.spent_usd === Math.round((3.75 + 0.4 + 20) * 100) / 100 && r.total.cap_usd === 60, "total = services + confirmed fixed costs, default total cap 60");
ok(r.total.unconfirmed.join() === "Domain,Phone", "unconfirmed fixed costs are listed, not added");
const r2 = spendReport({ now, env: {}, ai: { error: "timed out" }, agent: null, fixed: [] });
ok(r2.services[0].spent_usd === null && r2.total.level === "unknown" && /could not be read/.test(r2.total.words), "an unreadable AI ledger is shown as unknown, never as 0");
ok(r2.services.find((s) => s.id === "agents")!.level === "off", "no agent ledger = not running");
const r3 = spendReport({ now, env: {}, ai: { rows: [["2026-11-02T00:00:00Z", "x", "", "", "", "", "", "", "31"]] }, agent: null, fixed: [] });
ok(r3.services[0].words === "stopped at the cap" && r3.services[0].cap_usd === 30, "default Anthropic cap 30: at 31 the line reads stopped at the cap");

const msg = capMessage(30.2, 30);
ok(msg.startsWith(CAP_REFUSAL) && /\$30\.20 of \$30\.00/.test(msg) && /ANTHROPIC_MONTHLY_CAP_USD/.test(msg), "the refusal message says what happened, the figures and the setting");
process.exit(fail ? 1 : 0);
