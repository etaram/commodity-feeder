// Economics of the panel's price estimate (public/panel.html, const ECON). Run: node tests/econ.test.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
const html = readFileSync(new URL("../public/panel.html", import.meta.url), "utf8");
const src = html.match(/const ECON = \{[\s\S]*?\n\};/)[0];
const ECON = new Function(src + "; return ECON;")();
const near = (a, b, tol = 1) => assert.ok(Math.abs(a - b) <= tol, `${a} != ${b}`);
// audit case: supplier 40,000,000 + freight 1,000,000, other 7%, duty 0%
const landed = ECON.landed(40e6, 1e6, 0, 0.07);
near(landed, 43_870_000);
// a genuine 50% gross margin is 87,740,000 (the old code gave 65,805,000 = 50% markup)
near(ECON.priceAtMargin(landed, 0.5), 87_740_000);
near(ECON.margin(87_740_000, landed), 0.5, 1e-9);
near(ECON.markup(87_740_000, landed), 1.0, 1e-9);
// the old result: 65,805,000 is 50% markup, about 33.3% gross margin
near(ECON.markup(65_805_000, landed), 0.5, 1e-9);
near(ECON.margin(65_805_000, landed), 1 / 3, 1e-9);
// bounds
assert.ok(Number.isNaN(ECON.priceAtMargin(100, 0.95)));
assert.ok(Number.isNaN(ECON.priceAtMargin(100, -0.1)));
near(ECON.priceAtMargin(100, 0), 100, 1e-9);
assert.ok(Number.isNaN(ECON.margin(0, 10)));
console.log("econ: 10 checks passed");
// deal cash flows (principal): 100k goods, 30% deposit day 0, balance day 30, freight 5k, customer pays day 90 at 120k
const base = { role: "principal", sale_price: 120000, cost_goods: 100000, freight: 5000, insurance: 0, deposit_pct: 30, deposit_day: 0, balance_day: 30, customer_day: 90, fin_rate_pct: 0, bank_pct: 0, duty_pct: 0, contingency_pct: 0 };
let d = ECON.deal(base);
near(d.gp, 15000); near(d.peak, 105000); assert.equal(d.peakDay, 30); assert.equal(d.exposure, 90);
// freight already in the quote is not counted twice
d = ECON.deal({ ...base, freight_in_quote: true }); near(d.gp, 20000); near(d.peak, 100000);
// financing 10%/yr on the negative balance: 30,000 x 30 days + 105,000 x 60 days, /365 x 10%
d = ECON.deal({ ...base, fin_rate_pct: 10 }); near(d.fin, (30000 * 30 + 105000 * 60) * 0.1 / 365, 0.01);
// unknown inputs stay zero cost, never NaN
d = ECON.deal({ role: "principal", sale_price: 1000, cost_goods: "" }); near(d.gp, 1000); assert.equal(d.peak, 0);
// agent: commission only, no capital
d = ECON.deal({ role: "agent", sale_price: 200000, commission_pct: 3, customer_day: 60 }); near(d.net, 6000); assert.equal(d.peak, 0);
console.log("deal cash flows: 9 checks passed");
