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
