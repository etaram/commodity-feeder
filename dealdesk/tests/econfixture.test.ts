// Release fixture F12 (spec section 13): a synthetic deal with a known answer. Test numbers, not a real deal.
// 100 t bought at USD 250/t, sold at USD 320/t, freight 3,000, inspection 500. Cash out 28,500 on day 0, cash in
// 32,000 on day 45, simple interest 12% actual/365: financing 421.64, contribution 3,078.36, peak funding 28,500.
import { cashCheck } from "@/lib/dealstate";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const near = (a: number, b: number) => Math.abs(a - b) < 0.005;
const cost = 100 * 250 + 3000 + 500, sale = 100 * 320;
const flows = [{ day: 0, amount: -cost }, { day: 45, amount: sale }];
const a = cashCheck(flows, 0.12, 30000);
ok(near(a.finance_cost, 421.64), `financing cost 421.64 (got ${a.finance_cost.toFixed(2)})`);
ok(near(sale - cost - a.finance_cost, 3078.36), `contribution 3,078.36 (got ${(sale - cost - a.finance_cost).toFixed(2)})`);
ok(Math.round(a.peak_funding) >= 28500 && a.peak_funding < 28925, `peak funding starts at 28,500 (got ${a.peak_funding.toFixed(2)}, includes accrued interest)`);
ok(a.funding_capacity === "within the stated limit", "within a 30,000 limit");
const b = cashCheck(flows, 0.12, 28000);
ok(b.funding_capacity === "exceeds the stated limit" && b.warnings.length > 0, "a 28,000 limit blocks readiness although the contribution is positive");
const r = cashCheck([...flows].reverse(), 0.12, 30000);
ok(near(r.finance_cost, a.finance_cost) && near(r.peak_funding, a.peak_funding), "input order does not change the result");
ok(cashCheck(flows, 0.12, null).funding_capacity === "unknown", "no funding limit given stays unknown, not assumed");
process.exit(fail ? 1 : 0);
