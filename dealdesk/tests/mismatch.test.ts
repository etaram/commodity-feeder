// Acceptance test F09 "Technical product mismatch". Run: npm test (tests/run-all.mjs)
//
// Every supplier row below is synthetic: fictional names on example.com, written for this test.
// "Qualified" means bucket "supported" - the only bucket the desk presents as a fit. "plausible" (worth verifying,
// with explicit gaps) and "related" (correct type named in the conflicts) stay discoverable but are not qualified;
// "incompatible" is dropped from results. No score or probability is asserted anywhere: the matcher produces none.
// Concepts are given by hand, as in supmatch.test.ts (the live query expansion needs the network).
import { BUCKET_RANK, classifyMatch, familiesFor, termRe, type MatchResult } from "@/lib/supmatch";
import { countIndependent, evidenceFamilies, type Evidence } from "@/lib/assertions";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const classify = (q: string, concepts: string[][], s: any): MatchResult =>
  classifyMatch(s, concepts.map((c) => c.map(termRe)), concepts.map(() => []), q, familiesFor(q));
const show = (m: MatchResult) => `${m.bucket} - ${m.why}${m.conflicts.length ? " | conflicts: " + m.conflicts.join("; ") : ""}${m.gaps.length ? " | gaps: " + m.gaps.join("; ") : ""}`;
const SPEC_GAP = /not stated \(|\) not stated|not evidenced|not confirmed|model is not stated/;
type Case = { s: any; m: MatchResult };
const run = (q: string, concepts: string[][], rows: any[]): Case[] => rows.map((s) => ({ s, m: classify(q, concepts, s) }));
/** a negative: never qualified, and the conflicts name what the company really is */
const negative = (q: string, c: Case, type: RegExp, buckets: string[] = ["related", "incompatible"]) =>
  ok(c.m.bucket !== "supported" && buckets.includes(c.m.bucket) && c.m.conflicts.some((x) => type.test(x)), `[${q}] ${c.s.n}: not qualified, typed ${type} -> ${show(c.m)}`);
/** a qualifier: supported, with no open specification gap and no real conflict */
const qualifies = (q: string, c: Case) =>
  ok(c.m.bucket === "supported" && !c.m.gaps.some((g) => SPEC_GAP.test(g)) && c.m.conflicts.every((x) => /\(also listed\)$/.test(x)), `[${q}] ${c.s.n}: qualifies -> ${show(c.m)}`);
/** product named but a requested condition is missing: plausible, with each missing condition as an explicit gap */
const gapped = (q: string, c: Case, gaps: RegExp[]) =>
  ok(c.m.bucket === "plausible" && gaps.every((g) => c.m.gaps.some((x) => g.test(x))), `[${q}] ${c.s.n}: not qualified, explicit gaps ${gaps.join(" ")} -> ${show(c.m)}`);
/** technical fit before ranking: ordered by bucket, the qualifiers come first and nothing else is in front of them */
const rankedFirst = (q: string, cases: Case[], names: string[]) => {
  const order = [...cases].sort((a, b) => BUCKET_RANK[a.m.bucket] - BUCKET_RANK[b.m.bucket]).map((x) => x.s.n);
  const supported = cases.filter((x) => x.m.bucket === "supported").map((x) => x.s.n).sort();
  ok(JSON.stringify(supported) === JSON.stringify([...names].sort()) && names.every((n) => order.indexOf(n) < names.length), `[${q}] only ${names.join(", ")} qualified, ranked ahead of every other row`);
};
const maker = (n: string, p: string, extra: object = {}) => ({ n, p, ty: "manufacturer", web: `https://${n.toLowerCase().replace(/[^a-z]+/g, "-")}.example.com`, wt: n, ...extra });

// ---- 1. granular agricultural urea, bagged fertilizer ----
{
  const q = "granular agricultural urea, bagged fertilizer", cc = [["urea"]];
  const r = run(q, cc, [
    maker("Lumera Skin Labs", "urea 10% skin cream, urea foot care lotion, moisturizers"),
    maker("Oxibrite Chemicals", "urea hydrogen peroxide (carbamide peroxide), chemical reagents", { ty: "trader" }),
    maker("Medipure Pharma", "pharmaceutical grade urea USP for medical infusion and diagnostic breath tests"),
    maker("Nitrofield Fertilizers", "granular urea 46% N fertilizer in 50 kg bags; anhydrous ammonia"),
    maker("Prillco Nitrogen", "prilled urea 46% nitrogen fertilizer in bulk"),
    maker("Greenacre Agro Inputs", "urea 46% nitrogen fertilizer"),
  ]);
  negative(q, r[0], /cosmetic urea/);
  negative(q, r[1], /peroxide/);
  negative(q, r[2], /pharmaceutical, medical or laboratory urea/);
  qualifies(q, r[3]);
  negative(q, r[4], /prilled urea stated, granular requested/, ["related"]);
  gapped(q, r[5], [/form \(granular\) not stated/, /packing \(bagged\) not stated/]);
  rankedFirst(q, r, ["Nitrofield Fertilizers"]);
}

// ---- 2. 50 Hz diesel generator 500 kVA, stated voltage and emission standard ----
{
  const q = "50 Hz diesel generator 500 kVA, 400/230 V, EU Stage IIIA emissions", cc = [["diesel"], ["generator", "genset", "generating set"]];
  const r = run(q, cc, [
    maker("Bluewake Reefer Lines", "refrigerated container shipping line; reefer containers with clip-on diesel genset power packs", { ty: "works/services", in: "shipping" }),
    maker("Sunny Oats Cereals", "breakfast cereals, granola and oat flakes; factory powered by a 500 kVA diesel generator, 50 Hz", { in: "food" }),
    maker("Sunny Oats Milling", "breakfast cereals and oat flakes", { in: "food", hs: "8502", hd: "Electric generating sets with diesel engines" }),
    maker("GenParts Depot", "spare parts for diesel generators: AVR, controllers, filters, canopies; generator accessories", { ty: "trader" }),
    maker("Voltamont Power Systems", "diesel generator sets 20-2000 kVA, 50 Hz and 60 Hz, 400/230 V, EU Stage IIIA compliant; generator spare parts"),
    maker("Kestrel Gensets", "diesel generators for industry and standby power, 50 Hz"),
    maker("Sixty Cycle Power", "diesel generators 100-800 kVA, 60 Hz, 480 V, EPA Tier 2"),
    maker("Minigen Works", "diesel generators 10-200 kVA, 50 Hz, 400/230 V, EU Stage IIIA"),
    maker("Kilowatt Brothers", "diesel generators 400 kW, 50 Hz, 400/230 V, EU Stage IIIA"),
  ]);
  negative(q, r[0], /transport context/, ["related"]);
  negative(q, r[1], /own use/, ["related"]);
  ok(r[2].m.bucket === "plausible" && r[2].m.gaps.some((g) => /only customs codes or headings/.test(g)) && r[2].m.gaps.some((g) => /rated power \(500 kVA\) not stated/.test(g)), `[${q}] ${r[2].s.n}: customs heading only, not qualified -> ${show(r[2].m)}`);
  negative(q, r[3], /accessories or spare parts/, ["related"]);
  qualifies(q, r[4]);
  ok(r[4].m.conflicts.some((x) => /accessories or spare parts.*\(also listed\)/.test(x)), `[${q}] ${r[4].s.n}: its spare-parts line is noted, not held against the generating sets`);
  // missing capacity, voltage and certification are explicit gaps, never assumed from "diesel generators"
  gapped(q, r[5], [/rated power \(500 kVA\) not stated/, /voltage \(400 V\) not stated/, /EU Stage IIIA not evidenced/]);
  ok(/specification is not evidenced/.test(r[5].m.why), `[${q}] ${r[5].s.n}: the reason says a requested specification is not evidenced`);
  negative(q, r[6], /60 Hz stated, 50 Hz requested/, ["related"]);
  ok(r[6].m.gaps.some((g) => /400 V not stated \(states 480 V\)/.test(g)) && r[6].m.gaps.some((g) => /EU Stage IIIA not evidenced/.test(g)), `[${q}] ${r[6].s.n}: other voltage and other emission scheme are gaps, not assumed equivalent`);
  negative(q, r[7], /500 kVA is outside the stated range \(10-200 kVA\)/, ["related"]);
  gapped(q, r[8], [/stated in kW only; 500 kVA depends on the power factor/]);
  rankedFirst(q, r, ["Voltamont Power Systems"]);
}

// ---- 3. SWRO 8-inch membrane for seawater desalination ----
{
  const q = "SWRO 8-inch membrane element for seawater desalination", cc = [["swro", "seawater reverse osmosis", "reverse osmosis", "ro"], ["membrane", "element"]];
  const r = run(q, cc, [
    maker("Torqline Auto Filters", "automotive oil filters, air filters and cabin filters; membrane fuel filters for trucks"),
    maker("Clearstrand Membranes", "hollow-fiber ultrafiltration (UF) modules and membrane systems; UF pretreatment for SWRO membrane plants"),
    maker("Fourline Membranes", "SWRO membrane elements 4-inch (4040) for seawater desalination"),
    maker("Brackwell Membranes", "brackish water reverse osmosis (BWRO) membrane elements 8-inch (8040)"),
    maker("Hydroflow Equipment", "borehole pumps, water storage tanks and water meters; pressure vessels for SWRO membrane desalination plants"),
    maker("Marisal Membranes", "SWRO spiral-wound membrane elements 8-inch (8040) for seawater desalination; UF modules; BWRO elements 4040"),
    maker("Osmora Membranes", "reverse osmosis membrane elements for seawater desalination"),
    maker("Twinline Membranes", "brackish water RO membrane elements 8040; SWRO membrane elements 4040"),
    maker("Plainwell Membranes", "reverse osmosis membrane elements"),
  ]);
  negative(q, r[0], /automotive filters/, ["incompatible"]);
  negative(q, r[1], /different membrane process \(UF/, ["related"]);
  negative(q, r[2], /4-inch element stated, 8-inch requested/, ["related"]);
  negative(q, r[3], /brackish-water \(BWRO\) membrane stated, seawater \(SWRO\) requested/, ["related"]);
  negative(q, r[4], /around the RO membrane, not the membrane element/, ["related"]);
  qualifies(q, r[5]);
  gapped(q, r[6], [/element size \(8-inch\) not stated/]);
  // each line is judged on its own: an 8-inch brackish line and a 4-inch seawater line do not add up to SWRO 8-inch
  negative(q, r[7], /stated, .* requested/, ["related"]);
  gapped(q, r[8], [/element size \(8-inch\) not stated/, /feed water \(seawater \(SWRO\)\) not stated/]);
  rankedFirst(q, r, ["Marisal Membranes"]);
}

// ---- 4. two web copies of one press release are one confirmation ----
// lib/assertions.ts already collapsed copies with the same document hash or the same host+path; a republished text on
// another site was counted twice. This is tested against the helper added for it: evidenceFamilies (same quoted text
// joins a family) and countIndependent built on it. It reads the stored excerpt; a rewritten article is not detected.
{
  const release = "Example Power Ltd today announced that its 500 kVA diesel generating sets have been certified to EU Stage IIIA and are available for delivery to utility customers across East Africa from the third quarter.";
  const wire: Evidence = { url: "https://newswire.example.com/releases/2026/example-power-stage-iiia", publisher: "newswire", excerpt: release };
  const reprint: Evidence = { url: "https://dailytrade.example.org/news/example-power-certified?utm_source=feed", publisher: "trade news site", excerpt: `PRESS RELEASE - ${release.replace("Ltd today", "Ltd  today")} (Source: Example Power)` };
  const registry: Evidence = { url: "https://registry.example.net/certificates/77", publisher: "certification registry", excerpt: "Certificate 77: Example Power Ltd, diesel generating sets 500 kVA, emission stage IIIA, issued 2026-03-01 by the notified body, valid until 2029-03-01." };
  ok(evidenceFamilies([wire, reprint]).length === 1 && countIndependent([wire, reprint]) === 1, "one press release on two sites is one source family, one confirmation");
  const fams = evidenceFamilies([wire, registry, reprint]);
  ok(fams.length === 2 && countIndependent([wire, registry, reprint]) === 2 && fams.some((f) => f.length === 2 && f.includes(wire) && f.includes(reprint)) && fams.some((f) => f.length === 1 && f[0] === registry), "the release (2 copies) and the registry entry are two families: 3 pieces of evidence, 2 confirmations");
  ok(countIndependent([{ url: "https://a.example.com/x", excerpt: "ISO 9001 certified" }, { url: "https://b.example.org/y", excerpt: "ISO 9001 certified" }]) === 2, "a short identical phrase on two sites is not treated as a copy");
  ok(countIndependent([{ url: "https://a.example.com/x" }, { url: "https://b.example.org/y" }]) === 2, "two sites with no stored text stay two sources (nothing is assumed either way)");
}

console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
