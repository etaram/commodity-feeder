// Release fixture F12 (spec section 13): a synthetic deal with a known answer. Test numbers, not a real deal.
// 100 t bought at USD 250/t, sold at USD 320/t, freight 3,000, inspection 500. Cash out 28,500 on day 0, cash in
// 32,000 on day 45, simple interest 12% actual/365: financing 421.64, contribution 3,078.36, peak funding 28,500.
import { cashCheck, econInputs, econTitle } from "@/lib/dealstate";
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
// provenance of the inputs (review finding 9): a default or an unlabelled value is an assumption, never a finding
const d = econInputs({ sale_price: 32000, cost_goods: 25000 });
ok(d.fin_rate_pct.value === 10 && d.fin_rate_pct.basis === "assumption" && d.customer_pay_day.value === 60 && d.customer_pay_day.basis === "assumption", "default financing 10% and payment day 60 are labelled assumption");
ok(d.cost_goods.basis === "assumption" && econTitle(d) === "Scenario estimate", "values without a stated basis are assumptions: Scenario estimate");
const all = { sale_price: 32000, cost_goods: 25000, freight: 3000, other_costs: 500, fin_rate_pct: 12, supplier_pay_day: 0, customer_pay_day: 45 };
const claims = { sale_price: "confirmed", cost_goods: "quote", freight: "quote", other_costs: "confirmed", fin_rate_pct: "confirmed", supplier_pay_day: "confirmed", customer_pay_day: "confirmed" };
ok(econTitle(econInputs(all, claims, true)) === "Estimate from quotes", "every input a quote or confirmed: Estimate from quotes");
const nq = econInputs(all, claims, false);
ok(nq.cost_goods.basis === "assumption" && econTitle(nq) === "Scenario estimate", "a quote label without a recorded quote is downgraded to assumption");
ok(econTitle(econInputs(all, { ...claims, freight: "benchmark" }, true)) === "Scenario estimate", "a benchmark input keeps the result a scenario");
ok(econInputs(all, { ...claims, freight: "certain" }, true).freight.basis === "assumption", "an unknown label is an assumption");
const e = econInputs(all, claims, true), c2 = cashCheck([{ day: e.supplier_pay_day.value, amount: -(e.cost_goods.value + e.freight.value + e.other_costs.value) }, { day: e.customer_pay_day.value, amount: e.sale_price.value }], e.fin_rate_pct.value / 100, null);
ok(near(c2.finance_cost, 421.64), "labelled inputs give the same arithmetic as F12");
process.exit(fail ? 1 : 0);
