// Search correctness: Hebrew queries and strict product matching. Run: npx tsx tests/search.test.ts
import assert from "node:assert/strict";
import { allWordsRe, toEnglish, NON_LATIN } from "../lib/qtranslate";
(async () => {
  delete process.env.ANTHROPIC_API_KEY; // dictionary path only, no network
  assert.equal((await toEnglish("גנרטור")).text, "generator");
  assert.equal((await toEnglish("גנרטור דיזל")).text, "diesel generator");
  assert.equal((await toEnglish("התפלה")).text, "desalination");
  assert.equal((await toEnglish("diesel generator")).how, "none");
  assert.equal((await toEnglish("ציוד לא מוכר בכלל")).how, "failed"); // no AI key: keeps the text, says so
  assert.ok(NON_LATIN.test("שואבי אבק") && !NON_LATIN.test("vacuum"));
  const re = allWordsRe("diesel generator")!;
  assert.ok(re.test("supply of 500 kva diesel generator sets"));
  assert.ok(re.test("generator, diesel, 3 phase"));
  assert.ok(!re.test("ozone generator for water treatment"));
  assert.ok(!re.test("diesel fuel supply"));
  assert.ok(!re.test("dieselgeneratorx")); // word start only
  console.log("search: 11 checks passed");
})();
