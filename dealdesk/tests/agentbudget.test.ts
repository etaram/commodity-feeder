// The agents' hard spend cap (lib/agentbudget.ts): in-memory ledger, no network. Every refusal reason, the day
// boundary in Asia/Jerusalem, unknown spend staying at the worst case, and a real race of 20 reservations.
import { budgetConfig, budgetRowToCells, budgetView, cellsToBudgetRow, jerusalemDay, MemoryBudgetStore, reserve, settle, worstCase, type BudgetConfig, type BudgetRow, type BudgetStore } from "@/lib/agentbudget";
import { estimateCost } from "@/lib/anthropic";
import { sheetFor } from "@/lib/sheets";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const cfg: BudgetConfig = { dayUsd: 1, totalUsd: 5, from: "2026-11-12", until: "2026-11-14" };
const T = (iso: string) => Date.parse(iso);
const noon12 = T("2026-11-12T10:00:00Z"), noon13 = T("2026-11-13T10:00:00Z");
const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;

(async () => {
  // ---- defaults -------------------------------------------------------------------------------------------
  for (const k of ["AGENT_BUDGET_DAY_USD", "AGENT_BUDGET_TOTAL_USD", "AGENT_BUDGET_FROM", "AGENT_BUDGET_UNTIL"]) delete process.env[k];
  const d = budgetConfig();
  ok(d.dayUsd === 1 && d.totalUsd === 5 && d.from === "2026-11-12" && d.until === "2026-11-14", "defaults: 1 USD a day, 5 USD in total, 12 to 14 November 2026");
  process.env.AGENT_BUDGET_DAY_USD = "lots"; process.env.AGENT_BUDGET_FROM = "tomorrow";
  ok(budgetConfig().dayUsd === 0 && budgetConfig().from === "", "an unreadable setting closes the budget, it does not fall back to the default");
  delete process.env.AGENT_BUDGET_DAY_USD; delete process.env.AGENT_BUDGET_FROM;
  process.env.STATE_SHEET_ID = "state-sheet-for-test";
  ok(sheetFor("Agent Budget") === "state-sheet-for-test", "the ledger tab is registered as a state tab");
  delete process.env.STATE_SHEET_ID;

  // ---- worst case -----------------------------------------------------------------------------------------
  const wc = worstCase({ maxInputTokens: 16000, maxOutputTokens: 1500 });
  ok(wc > 0 && near(wc, estimateCost({ input_tokens: 16000, output_tokens: 1500 })), "worstCase uses the prices of lib/anthropic.ts");
  ok(worstCase({ maxInputTokens: 1000, maxOutputTokens: 100, maxSearches: 2 }) > worstCase({ maxInputTokens: 1000, maxOutputTokens: 100 }), "web searches add to the worst case");
  ok(worstCase({ maxInputTokens: NaN, maxOutputTokens: 100 }) === Infinity && worstCase({ maxInputTokens: 10, maxOutputTokens: Infinity }) === Infinity, "a missing limit makes the worst case infinite");

  // ---- day cap --------------------------------------------------------------------------------------------
  let s = new MemoryBudgetStore();
  const r1 = await reserve(s, { run: "a", role: "bd_research", worstCaseUsd: 0.4, now: noon12 }, cfg);
  const r2 = await reserve(s, { run: "a", role: "bd_opener", worstCaseUsd: 0.6, now: noon12 }, cfg);
  ok(r1.ok && r2.ok, "reservations up to exactly the day cap pass (0.40 + 0.60 = 1.00)");
  const r3 = await reserve(s, { run: "a", role: "evidence", worstCaseUsd: 0.01, now: noon12 }, cfg);
  ok(!r3.ok && r3.reason === "day_cap", "one cent more than the day cap is refused: day_cap");
  ok(s.rows.filter((r) => r.kind === "reserve").length === 2, "a refused call that could not fit writes no reservation row");
  ok((await reserve(s, { run: "a", role: "x", worstCaseUsd: 1.01, now: noon13 }, cfg)).ok === false, "a single call larger than the day cap is refused");

  // ---- total cap ------------------------------------------------------------------------------------------
  s = new MemoryBudgetStore();
  const big: BudgetConfig = { dayUsd: 1, totalUsd: 2.5, from: "2026-11-12", until: "2026-11-14" };
  const a1 = await reserve(s, { run: "t", role: "r", worstCaseUsd: 1, now: noon12 }, big);
  const a2 = await reserve(s, { run: "t", role: "r", worstCaseUsd: 1, now: noon13 }, big);
  const a3 = await reserve(s, { run: "t", role: "r", worstCaseUsd: 0.6, now: T("2026-11-14T10:00:00Z") }, big);
  ok(a1.ok && a2.ok && !a3.ok && (a3 as { reason: string }).reason === "total_cap", "the cumulative cap refuses on a day that still has room: total_cap");
  ok((await reserve(s, { run: "t", role: "r", worstCaseUsd: 0.5, now: T("2026-11-14T10:00:00Z") }, big)).ok, "what still fits under the total passes (2.00 + 0.50 = 2.50)");

  // ---- period ---------------------------------------------------------------------------------------------
  s = new MemoryBudgetStore();
  const out = async (iso: string) => reserve(s, { run: "p", role: "r", worstCaseUsd: 0.01, now: T(iso) }, cfg);
  const before = await out("2026-11-11T21:59:00Z"), first = await out("2026-11-11T22:00:00Z"), last = await out("2026-11-14T21:59:59Z"), after = await out("2026-11-14T22:00:00Z");
  ok(!before.ok && (before as { reason: string }).reason === "outside_period" && !after.ok && (after as { reason: string }).reason === "outside_period", "before the first day and after the last day: outside_period");
  ok(first.ok && last.ok, "the period is inclusive at both ends, in Asia/Jerusalem (00:00 on the 12th, 23:59:59 on the 14th)");
  ok(!(await reserve(s, { run: "p", role: "r", worstCaseUsd: 0.01, now: noon12 }, { ...cfg, from: "" })).ok, "a period that cannot be read refuses everything");

  // ---- unbounded ------------------------------------------------------------------------------------------
  for (const [v, name] of [[Infinity, "Infinity"], [NaN, "NaN"], [0, "0"], [-1, "negative"]] as [number, string][]) {
    const r = await reserve(s, { run: "u", role: "r", worstCaseUsd: v, now: noon12 }, cfg);
    ok(!r.ok && r.reason === "unbounded", `a worst case of ${name} is refused: unbounded`);
  }
  const u2 = await reserve(s, { run: "u", role: "r", worstCaseUsd: worstCase({ maxInputTokens: 1000, maxOutputTokens: NaN }), now: noon12 }, cfg);
  ok(!u2.ok && u2.reason === "unbounded", "a call without an output limit cannot reserve");

  // ---- unreadable ledger ----------------------------------------------------------------------------------
  const dead: BudgetStore = { list: async () => { throw new Error("Sheets 503"); }, append: async () => {} };
  const dr = await reserve(dead, { run: "d", role: "r", worstCaseUsd: 0.01, now: noon12 }, cfg);
  ok(!dr.ok && dr.reason === "ledger_unreadable", "a ledger that cannot be read refuses: ledger_unreadable");
  s = new MemoryBudgetStore();
  s.rows.push({ time: "2026-11-12T08:00:00.000Z", token: "t-bad", kind: "reserve", run: "", role: "", usd: NaN, note: "" });
  const br = await reserve(s, { run: "d", role: "r", worstCaseUsd: 0.01, now: noon12 }, cfg);
  ok(!br.ok && br.reason === "ledger_unreadable", "a reservation row whose amount cannot be read is not counted as zero: refused");
  ok((await budgetView(s, noon12, cfg)).readable === false && (await budgetView(s, noon12, cfg)).remaining_usd === 0, "the view of an unreadable ledger shows nothing left");
  // the read-back after the append fails: refused, and a release row is attempted
  let reads = 0; const mem = new MemoryBudgetStore();
  const flaky: BudgetStore = { list: async () => { if (++reads > 1) throw new Error("timeout"); return mem.list(); }, append: (r) => mem.append(r) };
  const fr = await reserve(flaky, { run: "d", role: "r", worstCaseUsd: 0.2, now: noon12 }, cfg);
  ok(!fr.ok && fr.reason === "ledger_unreadable" && mem.rows.map((r) => r.kind).join(",") === "reserve,release", "a failed read-back refuses the call and releases the row it wrote");
  // an append that silently drops the row: my row is missing in the read-back
  const lossy: BudgetStore = { list: async () => [], append: async () => {} };
  const lr = await reserve(lossy, { run: "d", role: "r", worstCaseUsd: 0.2, now: noon12 }, cfg);
  ok(!lr.ok && lr.reason === "ledger_unreadable", "a reservation that is not in the ledger after the append is refused");
  const noWrite: BudgetStore = { list: async () => [], append: async () => { throw new Error("read-only"); } };
  ok(!(await reserve(noWrite, { run: "d", role: "r", worstCaseUsd: 0.2, now: noon12 }, cfg)).ok, "a ledger that cannot be written refuses");

  // ---- settle: known, unknown, retry ----------------------------------------------------------------------
  s = new MemoryBudgetStore();
  const k1 = await reserve(s, { run: "s", role: "r", worstCaseUsd: 0.5, now: noon12 }, cfg);
  let v = await budgetView(s, noon12, cfg);
  ok(k1.ok && near(v.today.reserved_usd, 0.5) && near(v.today.spent_usd, 0) && near(v.remaining_today_usd, 0.5), "an open reservation counts at its reserved amount");
  if (k1.ok) await settle(s, k1.token, 0.03, noon12 + 1000);
  v = await budgetView(s, noon12, cfg);
  ok(near(v.today.spent_usd, 0.03) && near(v.today.reserved_usd, 0) && near(v.remaining_today_usd, 0.97) && near(v.remaining_total_usd, 4.97), "a settled call counts at its actual cost and frees the rest");
  const k2 = await reserve(s, { run: "s", role: "r", worstCaseUsd: 0.5, now: noon12 }, cfg);
  const st = k2.ok ? await settle(s, k2.token, null, noon12 + 2000) : null;
  v = await budgetView(s, noon12, cfg);
  ok(!!st && st.known === false && near(v.today.reserved_usd, 0.5) && near(v.remaining_today_usd, 0.47), "unknown spend stays counted at the worst case");
  if (k2.ok) await settle(s, k2.token, NaN, noon12 + 2500);
  ok(near((await budgetView(s, noon12, cfg)).today.reserved_usd, 0.5), "a cost that is not a number is unknown too");
  const k3 = await reserve(s, { run: "s", role: "r", worstCaseUsd: 0.4, now: noon12 }, cfg);
  ok(k2.ok && k3.ok && k3.token !== k2.token && s.rows.filter((r) => r.kind === "reserve").length === 3, "a retry is a new reservation with its own token, on top of the failed one");
  const k4 = await reserve(s, { run: "s", role: "r", worstCaseUsd: 0.1, now: noon12 }, cfg);
  ok(!k4.ok && k4.reason === "day_cap", "the failed call and its retry both count: 0.03 + 0.50 + 0.40 leaves no room for 0.10");
  await settle(s, "no-such-token", 0, noon12);
  ok(near((await budgetView(s, noon12, cfg)).remaining_today_usd, 0.07), "a settle row for a token that never reserved changes nothing");

  // ---- day reset at midnight in Asia/Jerusalem (22:00 UTC in winter) --------------------------------------
  ok(jerusalemDay(T("2026-11-12T21:59:59Z")) === "2026-11-12" && jerusalemDay(T("2026-11-12T22:00:00Z")) === "2026-11-13", "the day changes at 22:00 UTC in winter");
  ok(jerusalemDay(T("2026-07-01T20:59:59Z")) === "2026-07-01" && jerusalemDay(T("2026-07-01T21:00:00Z")) === "2026-07-02", "and at 21:00 UTC in summer");
  s = new MemoryBudgetStore();
  const m1 = await reserve(s, { run: "m", role: "r", worstCaseUsd: 1, now: T("2026-11-12T21:30:00Z") }, cfg);
  const m2 = await reserve(s, { run: "m", role: "r", worstCaseUsd: 0.2, now: T("2026-11-12T21:59:59Z") }, cfg);
  const m3 = await reserve(s, { run: "m", role: "r", worstCaseUsd: 0.2, now: T("2026-11-12T22:00:00Z") }, cfg);
  ok(m1.ok && !m2.ok && (m2 as { reason: string }).reason === "day_cap" && m3.ok, "a full day refuses at 23:59:59 local and a new day starts at 00:00 local");
  // settled after midnight: the cost stays on the day the call was reserved
  if (m1.ok) await settle(s, m1.token, 0.9, T("2026-11-12T22:05:00Z"));
  const v12 = await budgetView(s, T("2026-11-12T21:59:00Z"), cfg), v13 = await budgetView(s, T("2026-11-12T22:10:00Z"), cfg);
  ok(near(v12.today.spent_usd, 0.9) && near(v13.today.spent_usd, 0) && near(v13.today.reserved_usd, 0.2) && near(v13.total.spent_usd, 0.9), "a call settled after midnight still belongs to the day it was reserved on");

  // ---- the race: 20 roles at the same moment, 0.30 each, 1.00 a day ---------------------------------------
  const wait = () => new Promise<void>((r) => setTimeout(r, Math.floor(Math.random() * 6)));
  class SlowStore implements BudgetStore {
    rows: BudgetRow[] = []; peak = 0;
    async list() { await wait(); const copy = this.rows.map((r) => ({ ...r })); await wait(); return copy; }
    async append(row: BudgetRow) { await wait(); this.rows.push({ ...row }); await wait(); }
  }
  let allThree = true, neverOver = true, interleaved = false;
  for (let round = 0; round < 15; round++) {
    const slow = new SlowStore();
    const res = await Promise.all(Array.from({ length: 20 }, (_, i) => reserve(slow, { run: `race-${i}`, role: "bd_opener", worstCaseUsd: 0.3, now: noon12 }, cfg)));
    const won = res.filter((r) => r.ok);
    if (won.length !== 3) allThree = false;
    // what the ledger counts once every loser has released: only the winners
    const view = await budgetView(slow, noon12, cfg);
    if (view.today.reserved_usd > 1 + 1e-9 || !near(view.today.reserved_usd, 0.3 * won.length)) neverOver = false;
    const released = new Set(slow.rows.filter((r) => r.kind === "release").map((r) => r.token));
    if (won.some((r) => r.ok && released.has(r.token))) neverOver = false;
    if (slow.rows.filter((r) => r.kind === "reserve").length > 3) interleaved = true; // more than three rows landed before anyone verified: the race was real
    const rf = res.filter((r) => !r.ok) as { reason: string }[];
    if (rf.some((r) => r.reason !== "day_cap")) allThree = false;
  }
  ok(allThree, "20 concurrent reservations of 0.30 against 1.00: exactly 3 succeed, in every one of 15 rounds, the rest refused with day_cap");
  ok(neverOver, "after the race the ledger counts only the winners and never more than the cap");
  ok(interleaved, "the race was real: losing reservations did reach the ledger before they were released");

  // ---- sheet cells ----------------------------------------------------------------------------------------
  const row: BudgetRow = { time: "2026-11-12T10:00:00.000Z", token: "tok", kind: "reserve", run: "run-1", role: "evidence", usd: 0.0235, note: "" };
  const back = cellsToBudgetRow(budgetRowToCells(row));
  ok(!!back && back.usd === 0.0235 && back.kind === "reserve" && back.token === "tok" && typeof budgetRowToCells(row)[5] === "string", "a row survives the sheet: the amount is stored as text with a dot");
  ok(cellsToBudgetRow(["#"]) === null && cellsToBudgetRow(budgetRowToCells({ ...row, kind: "settle", usd: null }))!.usd === null, "the marker row is skipped and an unknown settle reads back as unknown");
  ok(Number.isNaN(cellsToBudgetRow(["2026-11-12T10:00:00.000Z", "t", "reserve", "", "", "0,30", ""])!.usd as number), "an amount with a comma is unreadable, not zero");

  process.exit(fail ? 1 : 0);
})();
