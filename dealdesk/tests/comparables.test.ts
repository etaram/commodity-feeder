// Comparable public awards (F11, corpus A). All rows are synthetic fixtures in the shape of the public award feed.
import { awardKey, comparableAwards, STATEMENT, type AwardRow } from "@/lib/comparables";
import { caseStatus } from "@/lib/outcomes";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const throws = (f: () => unknown) => { try { f(); return false; } catch { return true; } };
const row = (published: string, title: string, value_usd: number | null, winners: string[] | string, over: Partial<AwardRow> = {}): AwardRow =>
  ({ published, title, value_usd, country: "KEN", buyer: "Fixture Water Authority", winners, ...over });
const rows: AwardRow[] = [
  row("2021-03-01", "Supply of HDPE pipes, lot 1", 100_000, ["Alpha Pipes Ltd"]),
  row("2021-09-10", "Supply of HDPE pipes and fittings", 300_000, "Alpha Pipes Limited; Beta Plastics SARL"),
  row("2022-02-02", "HDPE pipes for the northern network", 500_000, ["Beta Plastics"]),
  row("2022-07-07", "Supply of HDPE Pipes - phase 2", 700_000, ["Gamma Industries"]),
  row("2023-01-15", "Delivery of HDPE pipes", 900_000, ["Alpha Pipes Ltd"]),
  row("2023-06-15", "Supply of HDPE pipes, lot 4", 1_100_000, ["Alpha Pipes Ltd"]),                 // the 2023 award used in the backtest
  row("2023-06-15", "SUPPLY OF HDPE PIPES - LOT 4", null, ["Alpha Pipes Ltd"], { source: "second-portal" }),   // second notice of the same award
  row("2024-04-02", "Supply of HDPE pipes, lot 5", 5_000_000, ["Delta Trading"]),
  row("2022-05-05", "Supply of steel pipes", 2_000_000, ["Gamma Industries"]),
  row("2022-06-06", "Supply of HDPE pipes", 400_000, ["Omega GmbH"], { country: "UGA", buyer: "Other Fixture Utility" }),
  row("", "Supply of HDPE pipes, undated", 1, ["Nobody"]),
];

const all = comparableAwards({ words: "hdpe pipes", country: "ken" }, rows, "2026-11-11");
ok(all.kind === "public_award_history" && all.statement === STATEMENT && STATEMENT === "public award history, not Sinder outcomes", "the result says what it is: public award history, not Sinder outcomes");
ok(all.n === 7 && all.excluded.duplicate_notices === 1, "two notices of one award count once");
const lot4 = all.rows.find((r) => /lot 4/i.test(r.title));
ok(lot4?.notices === 2 && lot4.value_usd === 1_100_000, "the merged award keeps the stated value and the notice count");
ok(awardKey(rows[5]) === awardKey(rows[6]) && awardKey(rows[5]) !== awardKey(rows[7]), "same buyer + same normalised title + same date is one award; another lot is another award");
ok(all.rows.every((r) => r.why.length === 2 && /title contains "hdpe", "pipes"/.test(r.why[0]) && r.why[1] === "country KEN"), "each row says why it matched");
ok(!all.rows.some((r) => /steel/.test(r.title) || r.country === "UGA"), "rows that miss a word or the country are left out");
ok(all.excluded.undated === 1, "an undated row is excluded and counted");
ok(JSON.stringify(all.by_year) === JSON.stringify({ "2021": 2, "2022": 2, "2023": 2, "2024": 1 }), "counts by year");
ok(all.by_winner[0].name === "Alpha Pipes Ltd" && all.by_winner[0].awards === 4 && all.by_winner.find((w) => /Beta/.test(w.name))?.awards === 2, "counts by winner group legal-name variants (Ltd / Limited, SARL)");
ok(all.value_usd.n === 7 && all.value_usd.min === 100_000 && all.value_usd.median === 700_000 && all.value_usd.max === 5_000_000, "value range: min, median, max with n");
ok(all.rows[0].published === "2024-04-02", "newest first");

// point in time: the 2023 award backtested with what was public before it
const pit = comparableAwards({ words: ["HDPE", "pipes"], country: "KEN" }, rows, "2023-06-14");
ok(pit.n === 5 && pit.excluded.published_after_as_of === 3 && !pit.rows.some((r) => r.published >= "2023-06-15"), "awards published after asOf are excluded (the 2023 award itself and the 2024 win)");
ok(!pit.by_winner.some((w) => w.name === "Delta Trading") && pit.by_winner[0].awards === 3 && pit.value_usd.median === 500_000, "the 2024 winner and its value do not enter the 2023 view");
ok(comparableAwards({ words: "hdpe" }, rows, "2023-06-15T00:00:00Z").rows.some((r) => /lot 4/i.test(r.title)), "an award published on the asOf day is included");

// small samples
const small = comparableAwards({ words: "hdpe pipes", country: "KEN", from: "2021-01-01", to: "2022-12-31" }, rows, "2026-11-11");
ok(small.n === 4 && small.rows.length === 4 && small.value_usd.median === null && small.value_usd.min === 100_000 && small.value_usd.max === 700_000 && /no median/.test(small.value_usd.note), "n < 5: rows are returned, no median");
ok(small.rows.every((r) => r.why.includes("published 2021-01-01 to 2022-12-31")), "the period is part of the reason");
const noVal = comparableAwards({ words: "hdpe pipes", country: "KEN" }, rows.map((r, i) => (i < 4 ? { ...r, value_usd: null } : r)), "2026-11-11");
ok(noVal.n === 7 && noVal.value_usd.n === 3 && noVal.value_usd.median === null, "seven awards but only three stated values: still no median");
const usd = comparableAwards({ buyer: "Other Fixture Utility Ltd" }, [row("2022-06-06", "x y", null, [], { buyer: "Other Fixture Utility", value: "400000", currency: "usd" }), row("2022-06-07", "x z", null, [], { buyer: "Other Fixture Utility", value: 9, currency: "EUR" })], "2026-11-11");
ok(usd.n === 2 && usd.rows.find((r) => r.title === "x y")?.value_usd === 400_000 && usd.rows.find((r) => r.title === "x z")?.value_usd === null, "buyer match ignores legal suffixes; a non-USD value is not converted here");
const empty = comparableAwards({ words: "desalination membranes" }, rows, "2026-11-11");
ok(empty.n === 0 && empty.rows.length === 0 && empty.value_usd.min === null && empty.statement === STATEMENT, "no match returns an empty, still labelled result");
ok(throws(() => comparableAwards({}, rows, "2026-11-11")) && throws(() => comparableAwards({ words: "hdpe" }, rows, "last year")) && throws(() => comparableAwards({ from: "2021" }, rows, "2026-11-11")), "an empty query, an unreadable asOf or a bad period is refused");

// no forecast language, and no bridge from a public winner to our own outcomes
ok(!/probab|win[ _-]?chance|likelihood|odds|score|predict/i.test(JSON.stringify(all)), "the output carries no probability, score or win-chance field");
ok(caseStatus([], "2026-11-11T00:00:00Z", 14).label === "not_contacted", "matched public awards create no ledger events: the case is still not_contacted");

console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
