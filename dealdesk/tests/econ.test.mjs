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
// provenance: a default is an assumption until the user confirms it, and it decides the title of the result
assert.equal(ECON.title({ cost: "confirmed", freight: "assumption" }), "scenario");
assert.equal(ECON.title({ cost: "quote", freight: "benchmark" }), "scenario");
assert.equal(ECON.title({ cost: "quote", freight: "confirmed" }), "quotes");
assert.equal(ECON.title({}), "scenario");
let b = ECON.basis({ role: "principal", sale_price: "120000", cost_goods: "100000", freight: "", freight_in_quote: false, fin_rate_pct: "" }, 100000);
assert.equal(b.sale_price, "confirmed"); assert.equal(b.cost_goods, "quote"); assert.equal(b.freight, "assumption"); assert.equal(b.fin_rate_pct, "assumption"); assert.equal(b.customer_day, "assumption");
assert.equal(ECON.title(b), "scenario");
b = ECON.basis({ role: "principal", sale_price: 1, cost_goods: 99, freight_in_quote: true, insurance_in_quote: true, inspection: 0, duty_pct: 0, contingency_pct: 0, bank_pct: 0, fin_rate_pct: 9, deposit_pct: 30, deposit_day: 0, balance_day: 30, customer_day: 90 }, 100);
assert.equal(b.cost_goods, "confirmed"); assert.equal(b.freight, "quote"); assert.equal(ECON.title(b), "quotes");
assert.equal(ECON.title(ECON.basis({ role: "agent", sale_price: 5, commission_pct: 3, customer_day: 60 })), "quotes");
// bidders: only a recorded count with its source; the engine default is unknown, never a number
assert.deepEqual(ECON.bidders({ est_bidders: "3.0", why: "deal $1 x net 5.0%; 3 bidders (buyer history); foreign win rate 4% (sector)" }), { n: 3, src: "buyer history" });
assert.equal(ECON.bidders({ est_bidders: "4.0", why: "4 bidders (default)" }).n, null);
assert.equal(ECON.bidders({ est_bidders: "", why: "" }).n, null);
assert.equal(ECON.bidders({ est_bidders: "5" }).n, null);
console.log("provenance: 17 checks passed");
// no win probability anywhere in the panel: no model, no input, no percentage row, no expected profit
for (const gone of ["winChance", "e-wown", "est_win", "est_ev", "est_best", "sc_pwin", "sc_ev", "win_chance:", "r.p_win_market", "Win chance", "win chance\"", "Expected profit", "model estimate, not a fact"])
  assert.ok(!html.includes(gone), `still in the panel: ${gone}`);
assert.ok(!/\bw \* pr\b|ev: isFinite\(w\)/.test(html), "expected profit from a win chance is still computed");
// the prefilled percentages come from ECON.DEFAULTS and carry an "assumption" label; the result is titled by its basis
assert.deepEqual(ECON.DEFAULTS, { freight_pct: 8, duty_pct: 0, other_pct: 7, bidders: 3 });
for (const id of ["e-fr", "e-duty", "e-oth"]) assert.ok(new RegExp(`id="${id}"[^>]*value="\\$\\{ECON\\.DEFAULTS\\.[a-z_]+\\}"[^>]*> <span class="pill warn" id="${id}-b">\\$\\{esc\\(t\\("b_assumption"\\)\\)\\}`).test(html), `${id} is not labelled`);
assert.ok(html.includes('t("ttl_" + ECON.title(basis))') && html.includes('t("ttl_" + ECON.title(bs))') && html.includes('t("no_pwin")'));
// bilingual: every new string exists once in English and once in Hebrew, and the two say the same thing
const str = k => [...html.matchAll(new RegExp(`(?<![A-Za-z0-9_])${k}: "((?:[^"\\\\]|\\\\.)*)"`, "g"))].map(m => m[1]);
for (const k of ["b_quote", "b_benchmark", "b_confirmed", "b_assumption", "b_blank", "ttl_scenario", "ttl_quotes", "bid_h", "bid_unknown", "bid_assumed", "no_pwin", "ev_basis", "est_inputs", "est_v_won", "est_ptw", "est_note2", "sc_n", "dw_e_note"]) {
  const v = str(k); assert.equal(v.length, 2, `${k}: ${v.length} strings`); assert.ok(/[a-z]/.test(v[0]) && /[֐-׿]/.test(v[1]) && !/[֐-׿]/.test(v[0]), `${k}: English then Hebrew`);
}
assert.deepEqual(str("ttl_scenario"), ["Scenario estimate", "אומדן תרחיש"]);
assert.ok(str("ttl_quotes")[0].startsWith("Estimate from quotes"));
assert.deepEqual(str("b_assumption"), ["assumption", "הנחה"]);
assert.ok(/No win probability is calculated/.test(str("no_pwin")[0]) && /לא מחושב סיכוי זכייה/.test(str("no_pwin")[1]));
for (const k of ["est_ptw"]) for (const v of str(k)) assert.ok(["{lo}", "{mid}", "{src}", "{n}", "{b}"].every(x => v.includes(x)), `${k} placeholders`);
console.log("labels and no win probability: 44 checks passed");
