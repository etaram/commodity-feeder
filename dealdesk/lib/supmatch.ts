import type { Supplier } from "@/lib/index";

// Supplier matching, stage C and E: does this company's evidence support THIS requirement, and why.
// Deterministic code, no model calls. Inputs are the query concepts (terms that must all be present) and one
// supplier record; output is one of four buckets with the evidence that put it there, the conflicts and the gaps.
//
//   supported  - the company's own product evidence (its products, industry, site title) names every concept
//                and nothing in it contradicts a mandatory requirement
//   plausible  - partial evidence: only customs headings, only contract titles, only some concepts, or the
//                company name; worth verifying, never presented as a fit
//   related    - a related product or an execution role (instrument transformers for a power-transformer query,
//                maize flour for whole maize, a genset in a reefer-shipping context, an installer)
//   incompatible - established conflict with a mandatory requirement (urea cream for fertilizer, steel pipe for
//                PE pipe); dropped from results
//
// Technical fit comes before ranking (acceptance test F09, tests/mismatch.test.ts): a requirement the request states
// (rated power, frequency, voltage, emission standard or certificate, membrane element size, feed water, urea form)
// must be stated by the supplier's evidence before the bucket can be "supported". A requirement the evidence
// contradicts makes the row "related"; one it does not mention is an explicit gap and the row is "plausible".
// Nothing is assumed from the product family, and no score is produced.
//
// The company name locates an entity; it never establishes product capability. HS/CPV codes are retrieval
// signals, not proof of compatibility. Terms match on whole words ("corn" is not in "Corning").
export const MATCH_VERSION = "match-1.5 (2026-11-11)";
export type Bucket = "supported" | "plausible" | "related" | "incompatible";
export type MatchResult = { bucket: Bucket; why: string; evidence: string; conflicts: string[]; gaps: string[]; url?: string };

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** whole-word (or whole-phrase) match; a trailing plural s/es is allowed, a longer word is not */
export function termRe(term: string): RegExp {
  const t = term.toLowerCase().trim().replace(/\s+/g, " ");
  const base = t.length > 4 && t.endsWith("s") && !t.endsWith("ss") ? t.slice(0, -1) : t;
  const body = base.split(" ").map(esc).join("[\\s\\-]+");
  return new RegExp(`(^|[^\\p{L}\\p{N}])${body}(e?s)?(?=$|[^\\p{L}\\p{N}])`, "iu");
}

// record: judged only against the whole record, where the right product stated elsewhere clears it (a maker of RO
// and UF membranes lists both in one item)
type Rule = { rx: RegExp; label: string; bucket: "related" | "incompatible"; record?: boolean };

// ---- technical specifications a request can state ----
type SpecState = "met" | "conflict" | "unstated";
type SpecReq = { blocking: boolean; check: (evidence: string) => { state: SpecState; note: string } };
// read: the requirements of this kind that the request states (none when it states none)
type Spec = { id: string; read: (query: string) => SpecReq[] };
const NUM = "(\\d{1,3}(?:,\\d{3})+|\\d+(?:\\.\\d+)?)";
const toNum = (x: string) => parseFloat(x.replace(/,/g, ""));
const fmt = (n: number) => String(Math.round(n * 100) / 100);

// rated power: kVA and MVA are one scale, kW and MW another; the two are never converted into each other here
// (the ratio is the power factor, which the evidence would have to state)
const P_UNIT = "(kva|mva|kw|mw)";
const pScale = (u: string) => ({ kind: /va$/i.test(u) ? "kVA" : "kW", mul: /^m/i.test(u) ? 1000 : 1 });
const powerSpec: Spec = { id: "rated-power", read: (q) => {
  const m = new RegExp(`${NUM}\\s?${P_UNIT}\\b`, "i").exec(q);
  if (!m) return [];
  const w = pScale(m[2]), want = toNum(m[1]) * w.mul, label = `${fmt(want)} ${w.kind}`;
  return [{ blocking: true, check: (ev) => {
    const iv: [number, number][] = [], pts: number[] = []; let other = false;
    for (const r of ev.matchAll(new RegExp(`${NUM}\\s?${P_UNIT}?\\s*(?:-|\u2013|\u2014|to|up to)\\s*${NUM}\\s?${P_UNIT}\\b`, "gi"))) {
      const hi = pScale(r[4]), lo = pScale(r[2] || r[4]);
      if (hi.kind === w.kind && lo.kind === w.kind) iv.push([toNum(r[1]) * lo.mul, toNum(r[3]) * hi.mul]);
    }
    for (const r of ev.matchAll(new RegExp(`(?:up to|max(?:imum)?\\.?|\u2264)\\s*${NUM}\\s?${P_UNIT}\\b`, "gi"))) { const u = pScale(r[2]); if (u.kind === w.kind) iv.push([0, toNum(r[1]) * u.mul]); }
    for (const r of ev.matchAll(new RegExp(`${NUM}\\s?${P_UNIT}\\b`, "gi"))) { const u = pScale(r[2]); if (u.kind === w.kind) pts.push(toNum(r[1]) * u.mul); else other = true; }
    if (iv.some(([a, b]) => want >= a && want <= b) || pts.includes(want)) return { state: "met", note: "" };
    const all = [...pts, ...iv.flat()];
    if (!all.length) return { state: "unstated", note: other ? `rated power is stated in ${w.kind === "kVA" ? "kW" : "kVA"} only; ${label} depends on the power factor and is not confirmed` : `rated power (${label}) not stated` };
    const lo = Math.min(...all), hi = Math.max(...all);
    if (want < lo || want > hi) return { state: "conflict", note: `rated power ${label} is outside the stated range (${lo === hi ? fmt(lo) : `${fmt(lo)}-${fmt(hi)}`} ${w.kind})` };
    return { state: "unstated", note: `a ${label} model is not stated (stated ratings: ${[...new Set(pts)].sort((a, b) => a - b).map(fmt).join(", ")} ${w.kind})` };
  } }];
} };
const frequencySpec: Spec = { id: "frequency", read: (q) => {
  const m = /\b(50|60)\s?hz\b/i.exec(q);
  if (!m) return [];
  return [{ blocking: true, check: (ev) => {
    const got = new Set<string>();
    for (const r of ev.matchAll(/\b(50|60)(?:\s*(?:\/|or|and|&)\s*(50|60))?\s?hz\b/gi)) { got.add(r[1]); if (r[2]) got.add(r[2]); }
    if (got.has(m[1])) return { state: "met", note: "" };
    return got.size ? { state: "conflict", note: `${[...got].join("/")} Hz stated, ${m[1]} Hz requested` } : { state: "unstated", note: `frequency (${m[1]} Hz) not stated` };
  } }];
} };
// voltage: a different stated voltage is reported as a gap, not a conflict (alternators are commonly reconnectable
// and 380/400/415 V are one class; the evidence has to say so before it counts)
const voltageSpec: Spec = { id: "voltage", read: (q) => {
  const m = new RegExp(`(?:^|[^\\d.,])${NUM}(?:\\s*\\/\\s*${NUM})?\\s?(kv|v|volts?)\\b`, "i").exec(q);
  if (!m) return [];
  const mul = (u: string) => (/^kv$/i.test(u) ? 1000 : 1), want = toNum(m[1]) * mul(m[3]);
  return [{ blocking: true, check: (ev) => {
    const pts: number[] = []; let hit = false;
    for (const r of ev.matchAll(new RegExp(`${NUM}(?:\\s*(\\/|-|\u2013|to)\\s*${NUM})?\\s?(kv|v|volts?)\\b`, "gi"))) {
      const a = toNum(r[1]) * mul(r[4]), b = r[3] ? toNum(r[3]) * mul(r[4]) : a;
      pts.push(a, b);
      if (r[2] && r[2] !== "/" ? want >= Math.min(a, b) && want <= Math.max(a, b) : a === want || b === want) hit = true;
    }
    if (hit) return { state: "met", note: "" };
    return { state: "unstated", note: pts.length ? `${fmt(want)} V not stated (states ${[...new Set(pts)].map(fmt).join(", ")} V)` : `voltage (${fmt(want)} V) not stated` };
  } }];
} };
// emission stages and certificates the request names: each must be named by the evidence, none is assumed
const ROMAN: Record<string, string> = { "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V" };
function standardsIn(t: string): string[] {
  const out: string[] = [];
  for (const r of t.matchAll(/\b(?:eu[\s-]+)?stage[\s-]?(iii\s?[ab]|iii|ii|iv|v|i|[1-5]\s?[ab]?)\b/gi)) { const x = r[1].replace(/\s/g, "").toUpperCase(); out.push(`EU Stage ${x.replace(/^[1-5]/, (d) => ROMAN[d])}`); }
  for (const r of t.matchAll(/\b(?:epa[\s-]+)?tier[\s-]?([1-4])(?:\s?(final|interim))?\b/gi)) out.push(`EPA Tier ${r[1]}${r[2] ? " " + r[2].toLowerCase() : ""}`);
  for (const r of t.matchAll(/\biso[\s-]?(\d{4,5})\b/gi)) out.push(`ISO ${r[1]}`);
  for (const r of t.matchAll(/\bnsf(?:\s?\/\s?ansi)?[\s-]?(\d{2,3})\b/gi)) out.push(`NSF/ANSI ${r[1]}`);
  return [...new Set(out)];
}
const standardSpec: Spec = { id: "standard", read: (q) => standardsIn(q).map((want) => ({ blocking: true, check: (ev: string) => {
  const got = standardsIn(ev);
  // "Tier 4" in the request is met by "Tier 4 final"; the reverse is not
  if (got.some((g) => g === want || (/^EPA Tier \d$/.test(want) && g.startsWith(want + " ")))) return { state: "met" as const, note: "" };
  const same = got.filter((g) => g.split(" ")[0] === want.split(" ")[0]);
  return { state: "unstated" as const, note: `${want} not evidenced${same.length ? ` (states ${same.join(", ")})` : ""}` };
} })) };
// RO element diameter, as inches or as the model code (8040 = 8 x 40 inch)
const ELEMENT_CODE: Record<string, string> = { "2540": "2.5", "4040": "4", "4021": "4", "8040": "8", "8080": "8", "1640": "16" };
function elementSizes(t: string): string[] {
  const out: string[] = [];
  for (const r of t.matchAll(/(?:^|[^\d.])(2\.5|4|8|16)[\s-]?(?:inch(?:es)?\b|["\u201d\u2033])/gi)) out.push(r[1]);
  for (const r of t.matchAll(/(?:^|[^\d])(2540|4040|4021|8040|8080|1640)(?!\d)/g)) out.push(ELEMENT_CODE[r[1]]);
  return [...new Set(out)];
}
const elementSizeSpec: Spec = { id: "element-size", read: (q) => {
  const want = elementSizes(q)[0];
  if (!want) return [];
  return [{ blocking: true, check: (ev) => {
    const got = elementSizes(ev);
    if (got.includes(want)) return { state: "met", note: "" };
    return got.length ? { state: "conflict", note: `${got.join("- and ")}-inch element stated, ${want}-inch requested` } : { state: "unstated", note: `element size (${want}-inch) not stated` };
  } }];
} };
const SEA = /\bswro\b|\bsea[\s-]?water\b/i, BRACKISH = /\bbwro\b|\bbrackish\b/i;
const feedWaterSpec: Spec = { id: "feed-water", read: (q) => {
  const sea = SEA.test(q), br = BRACKISH.test(q);
  if (sea === br) return [];
  const [mine, theirs, want, got] = sea ? [SEA, BRACKISH, "seawater (SWRO)", "brackish-water (BWRO)"] : [BRACKISH, SEA, "brackish water (BWRO)", "seawater (SWRO)"];
  return [{ blocking: true, check: (ev) => mine.test(ev) ? { state: "met", note: "" }
    : theirs.test(ev) ? { state: "conflict", note: `${got} membrane stated, ${want} requested` } : { state: "unstated", note: `feed water (${want}) not stated` } }];
} };
const ureaFormSpec: Spec = { id: "urea-form", read: (q) => {
  const m = /\b(granular|prilled)\b/i.exec(q);
  if (!m) return [];
  const want = m[1].toLowerCase(), alt = want === "granular" ? "prilled" : "granular";
  return [{ blocking: true, check: (ev) => new RegExp(`\\b${want}\\b`, "i").test(ev) ? { state: "met", note: "" }
    : new RegExp(`\\b${alt}\\b`, "i").test(ev) ? { state: "conflict", note: `${alt} urea stated, ${want} requested` } : { state: "unstated", note: `form (${want}) not stated` } }];
} };
// packing is a commercial condition: reported as a gap when not stated, it never changes the bucket
const packingSpec: Spec = { id: "packing", read: (q) => {
  if (!/\b(bagged|in bags|bags)\b/i.test(q)) return [];
  return [{ blocking: false, check: (ev) => /\b(bag(s|ged)?|sacks?|\d+ ?kg)\b/i.test(ev) ? { state: "met", note: "" } : { state: "unstated", note: "packing (bagged) not stated" } }];
} };

const AUTOMOTIVE_FILTERS: Rule = { rx: /\b(oil filters?|air filters?|fuel filters?|cabin filters?|automotive|auto parts|car parts|spare parts for (cars|trucks|vehicles)|for (cars|trucks|vehicles|motorcycles))\b/i, label: "automotive filters, not RO water treatment", bucket: "incompatible" };
// parts and accessories of a generating set, and a generating set the company runs for itself
const GEN_PARTS = "(spare parts?|parts|accessor\\w*|components?|consumables|filters?|controllers?|control panels?|avrs?|canop(y|ies)|silencers?|mufflers?|radiators?|transfer switch\\w*|batter(y|ies)|fuel tanks?)";
const GEN_NOUN = "(generators?|gensets?|generating sets?)";
const GEN_ACCESSORY = `\\b${GEN_PARTS} (for|of|to suit)\\b[^;,]{0,40}\\b${GEN_NOUN}\\b|\\b${GEN_NOUN} ${GEN_PARTS}\\b`;
const GEN_OWN_USE = `\\b(powered by|runs? on|running on|backed[- ]up by|backup (power )?from|equipped with|fitted with|our own|own[- ]use|on-?site)\\b[^;,]{0,40}\\b${GEN_NOUN}\\b`;
// equipment, pretreatment and consumables around an RO membrane
const RO_AROUND = "\\b(pre-?treatment|housings?|pressure vessels?|pumps?|valves?|skids?|racks?|antiscalants?|chemicals?|cleaners?|energy recovery( devices?)?|cartridges?|filters?|dosing( systems?)?|spare parts?|services?) (for|before|upstream of|ahead of)\\b[^;,.]{0,60}";
// exact: the right product stated outright; strip: phrases removed before that test (in "maize flour" the word
// maize names flour, not grain)
type Family = { id: string; when: RegExp; need?: { rx: RegExp; gap: string }; exact?: RegExp; strip?: RegExp; rules: Rule[]; specs?: Spec[] };
// Curated product families from the observed failures (urea, maize, generators, steel coil, transformers, PE pipe).
// "when" reads the query; rules read the supplier's evidence text. A rule fires only when the query does not ask
// for that product itself (a search for "urea cream" keeps cream makers).
const FAMILIES: Family[] = [
  { id: "urea-fertilizer", when: /\burea\b/i,
    exact: /\b(fertili[sz]\w*|granular urea|prilled urea|urea 46|agricultural urea|nitrogen fertili[sz]\w*)\b/i, strip: /\b(fertili[sz]er|paraben|fragrance)[- ]free\b/gi,
    need: { rx: /\b(fertili[sz]\w*|granular|prilled|agricultur\w*|nitrogen|46 ?%|ammonia|3102)\b/i, gap: "grade not stated (fertilizer, technical or automotive)" },
    rules: [
      { rx: /\b(cream|lotion|moisturi[sz]\w*|cosmetic\w*|skin|derma\w*|ointment|emollient|hand care|foot care)\b/i, label: "cosmetic urea, not fertilizer", bucket: "incompatible" },
      { rx: /\b(peroxide|carbamide peroxide|whitening|teeth)\b/i, label: "urea peroxide compound, not fertilizer", bucket: "incompatible" },
      { rx: /\b(pharma\w*|medical|medicinal|usp|ph\.? ?eur|bp grade|injection|infusion|diagnostic\w*|breath tests?|clinical|laborator\w*|reagents?|analytical grade)\b/i, label: "pharmaceutical, medical or laboratory urea, not fertilizer", bucket: "related" },
      { rx: /\b(urea[- ]formaldehyde|resins?|adhesives?|glue)\b/i, label: "urea resin or adhesive", bucket: "related" },
      { rx: /\b(adblue|def\b|diesel exhaust fluid)\b/i, label: "automotive urea solution", bucket: "related" },
    ], specs: [ureaFormSpec, packingSpec] },
  { id: "grain", when: /\b(maize|corn|wheat|rice|barley|sorghum|millet)\b/i,
    exact: /\b(maize|corn|wheat|rice|barley|sorghum|millet)\b(?![\s-]+(flour|meal|starch|syrup|gluten|bran|oil|flakes|grits|snacks?|chips|feed|silage|noodles?|crackers?|cakes?|vinegar|wine|paper|husk|straw))/i,
    strip: /\b(maize|corn|wheat|rice|barley)[\s-]+(flour|meal|starch|syrup|gluten|bran|oil|flakes|grits|snacks?|chips|feed|silage|noodles?|crackers?|cakes?|vinegar|wine|paper|husk|straw)\b|\b(sweet ?corn|popcorn|corn ?flakes|atta|maida|semolina)\b/gi,
    need: { rx: /\b(maize|corn)\b/i, gap: "maize not named in the company's own products" },
    rules: [
      { rx: /\b(flour|atta|maida|semolina|meal|starch|snacks?|chips|syrup|gluten|bran|popcorn|tortillas?|sweet ?corn|canned|corn oil|cornflakes?|grits|dextrose|noodles?|pasta|biscuits?|bakery)\b/i, label: "processed grain product, not the grain", bucket: "related" },
      { rx: /\b(animal feed|feed mill|silage|ddgs|by-?products?)\b/i, label: "feed or by-product", bucket: "related" },
    ] },
  { id: "sugar", when: /\bsugar\b/i,
    exact: /\b(cane sugar|beet sugar|white sugar|refined sugar|raw sugar|icumsa|sugar refin\w*|sugar mill)\b/i,
    rules: [{ rx: /\b(coconut sugar|palm sugar|date (paste|syrup)|sugar[- ]free|sweeteners?|confectioner\w*|candy|candies)\b/i, label: "a different sweetener or a sugar product", bucket: "related" }] },
  { id: "cement", when: /\bcement\b/i,
    exact: /\b(portland|opc|ppc|cem ?i|clinker|grey cement|cement plant|cement manufactur\w*)\b/i,
    rules: [{ rx: /\b(calcium aluminate|refractory|calcium carbonate|fillers?|cement boards?|fibre cement|fiber cement|adhesives?|grout)\b/i, label: "a specialty or related material, not bulk cement", bucket: "related" }] },
  { id: "ammonia", when: /\bammonia\b/i,
    rules: [
      { rx: /\b(ultra ?purity|ultima|electronic grade|reagent|laborator\w*|labochemicals|analytical grade|ammonium hydroxide|ammonia solution)\b/i, label: "laboratory or electronic grade, not bulk ammonia", bucket: "related" },
    ] },
  { id: "generator", when: /\b(generators?|gensets?|generating sets?)\b/i,
    exact: /\b(diesel|petrol|gasoline|natural gas|standby|silent|soundproof|power|electric(al)?) (generators?|gensets?|generating sets?)\b|\bgensets?\b|\bgenerating sets?\b/i,
    strip: new RegExp(`${GEN_ACCESSORY}|${GEN_OWN_USE}`, "gi"),
    specs: [powerSpec, frequencySpec, voltageSpec, standardSpec],
    rules: [
      { rx: new RegExp(GEN_ACCESSORY, "i"), label: "generator accessories or spare parts, not generating sets", bucket: "related" },
      { rx: new RegExp(GEN_OWN_USE, "i"), label: "runs a generator for its own use, does not sell them", bucket: "related" },
      { rx: /\b(reefer|clip-?on|refrigerated containers?|container gensets?|cold chain|freight|shipping line)\b/i, label: "genset named in a transport context, not sold", bucket: "related" },
      { rx: /\b(ozone|hydrogen|steam|nitrogen|oxygen|signal|function|smoke|foam|fog|wave|pulse|noise|vapou?r|ice) generators?\b/i, label: "a different kind of generator", bucket: "incompatible" },
      { rx: /\b(rental|hire)\b/i, label: "rental, not sale", bucket: "related" },
    ] },
  { id: "hot-rolled-coil", when: /\b(hot[- ]rolled|hrc)\b/i,
    exact: /\b(hot[- ]rolled|hrc)\b/i,
    need: { rx: /\b(hot[- ]rolled|hrc|hr coils?|7208)\b/i, gap: "hot-rolled not stated" },
    rules: [
      { rx: /\b(shoes?|footwear|boots|apparel|garments?|toys?)\b/i, label: "steel codes on a non-steel product", bucket: "incompatible" },
      { rx: /\b(cold[- ]rolled|crc|wire rods?|rebars?|plates?|galvani[sz]\w*|tinplate|stainless|pipes?|tubes?)\b/i, label: "a different steel product", bucket: "related" },
    ] },
  { id: "power-transformer", when: /\b(power|distribution) transformers?\b/i,
    exact: /\b(power|distribution) transformers?\b(?![\s-]+(protection|monitoring|testing|test|bushings?|oil|relays?))|\b\d+ ?(mva|kva)\b/i,
    need: { rx: /\b(power transformers?|distribution transformers?|mva|kva|oil[- ]immersed|dry[- ]type|transformer manufactur\w*)\b/i, gap: "transformer type and rating not stated" },
    rules: [
      { rx: /\b(instrument transformers?|current transformers?|voltage transformers?|potential transformers?)\b/i, label: "instrument transformers, not power", bucket: "related" },
      { rx: /\b(bushings?|tap[- ]changers?|transformer oil|radiators?|insulating oil)\b/i, label: "transformer accessories", bucket: "related" },
      { rx: /\b(installation|erection|commissioning|substation construction|epc|turnkey|civil works)\b/i, label: "project execution role (installer or EPC)", bucket: "related" },
      { rx: /\b(fire suppression|containment|filtration|protection systems?|monitoring systems?) (for|of)\b|\bfor (electrical |electric |power |distribution )*transformers\b/i, label: "systems for transformers, not transformers", bucket: "related" },
    ] },
  { id: "pe-pipe", when: /\b(pe|hdpe|mdpe|polyethylene|pe100|pe80|plastic) pipes?\b|\bpolyethylene\b/i,
    exact: /\b(polyethylene|hdpe|mdpe|pe ?100|pe ?80|pe pipes?)\b/i,
    need: { rx: /\b(polyethylene|hdpe|mdpe|pe ?100|pe ?80|pe pipes?|plastic pipes?|polypropylene|pvc)\b/i, gap: "pipe material not stated" },
    rules: [
      { rx: /\b(rails?|railway|sleepers)\b/i, label: "rail products, not pipe", bucket: "incompatible" },
      { rx: /\b(steel|ductile|cast iron|galvani[sz]\w*|copper)\b/i, label: "metal pipe or fittings, not PE", bucket: "related" },
      { rx: /\b(cable|couplings?|ducts?)\b/i, label: "cable or coupling products", bucket: "related" },
      { rx: /\b(water services?|leak detection|meter reading|installation|maintenance)\b/i, label: "water service provider", bucket: "related" },
    ] },
  // RO water treatment (skill sinder-counterpart-match, 6 Nov 2026): "RO" and "filters" pull in automotive filter makers
  { id: "ro-water", when: /\b(reverse osmosis|ro (plants?|systems?|units?|membranes?)|desalinat\w*)\b/i,
    exact: /\b(reverse osmosis|ro (plants?|systems?|units?|membranes?)|desalinat\w*|water treatment (plants?|systems?))\b/i,
    need: { rx: /\b(reverse osmosis|ro (plants?|systems?|units?|membranes?)|desalinat\w*|water treatment|membranes?)\b/i, gap: "RO water treatment not stated" },
    rules: [
      AUTOMOTIVE_FILTERS,
      { rx: /\b(household|domestic|home|under[- ]sink|countertop|kitchen) (water )?(purifiers?|filters?|systems?)\b|\bwater dispensers?\b/i, label: "household purifier, not an industrial RO system", bucket: "related" },
      { rx: /\b(bottled water|mineral water|drinking water brand)\b/i, label: "bottled water producer", bucket: "related" },
    ] },
  // RO membrane elements (F09): the element is the product; another membrane process, the wrong element size, the
  // wrong feed water and the equipment around the element are not
  { id: "ro-membrane", when: /\b(swro|bwro)\b|\b(ro|reverse osmosis|desalinat\w*)\b.*\b(membranes?|elements?)\b|\b(membranes?|elements?)\b.*\b(ro|reverse osmosis|desalinat\w*)\b/i,
    exact: /\b(swro|bwro|ro|reverse osmosis)\b[^;,.]{0,40}\b(membranes?|elements?)\b|\b(membranes?|elements?)\b[^;,.]{0,30}\b(swro|bwro|reverse osmosis)\b/i,
    strip: new RegExp(RO_AROUND, "gi"),
    need: { rx: /\b(membranes?|elements?)\b/i, gap: "membrane elements not stated" },
    specs: [elementSizeSpec, feedWaterSpec, standardSpec],
    rules: [
      AUTOMOTIVE_FILTERS,
      { rx: /\b(ultra-?filtration|micro-?filtration|nano-?filtration|uf|mf|nf|mbr)\b|\bhollow[- ]fib(er|re)\b/i, label: "a different membrane process (UF, MF or NF), not reverse osmosis", bucket: "related", record: true },
      { rx: new RegExp(RO_AROUND, "i"), label: "equipment or pretreatment around the RO membrane, not the membrane element", bucket: "related" },
    ] },
  // maize color is a specification, not a synonym: a yellow-maize seller is not an exact fit for white maize
  { id: "white-maize", when: /\bwhite (maize|corn)\b/i, exact: /\bwhite (maize|corn)\b/i,
    need: { rx: /\bwhite (maize|corn)\b/i, gap: "maize color not stated (white requested)" },
    rules: [{ rx: /\byellow (maize|corn)\b/i, label: "yellow maize, white requested", bucket: "related" }] },
  { id: "yellow-maize", when: /\byellow (maize|corn)\b/i, exact: /\byellow (maize|corn)\b/i,
    need: { rx: /\byellow (maize|corn)\b/i, gap: "maize color not stated (yellow requested)" },
    rules: [{ rx: /\bwhite (maize|corn)\b/i, label: "white maize, yellow requested", bucket: "related" }] },
];

// Rules for every request: the product named as the input of a machine, or around a project role, is not the
// product sold (ammunition production lines, LPG engines, ammonia fuel cells, solar EPC, excavator attachments)
const GENERIC: Family = { id: "generic", when: /./, rules: [
  { rx: /\b(machines?|machinery|production lines?|lines?|plants?|equipment|test(ing)? (equipment|systems?)|engines?|fuel cells?|attachments?|tiltrotators?|storage tanks?|terminals?|boards?) (for|that (use|run on)|running on|using|to (make|produce))\b/i, label: "equipment or parts for the product, not the product", bucket: "related" },
  { rx: /\b(fuel cells?|engines?) (powered by|fuel(l)?ed by)\b|\b(impregnated|coated) with\b/i, label: "uses the product as an input", bucket: "related" },
  { rx: /\b(epc|turnkey|ppa|rooftop installer|installs?|installation services|contractor for|substations? construction|builds? (substations|plants))\b/i, label: "project execution role (installer or EPC)", bucket: "related" },
  { rx: /\b(freight forward\w*|logistics provider|shipping agent|customs broker|household goods|personal effects)\b/i, label: "a logistics firm moving the goods", bucket: "related" },
  { rx: /\b(procurement (agent|intermediary|services)|sourcing agent|relief aid)\b/i, label: "a procurement intermediary", bucket: "related" },
] };

export function familiesFor(query: string): Family[] {
  return [...FAMILIES.filter((f) => f.when.test(query)), GENERIC];
}

const SERVICE_TYPE = /services/i;

// the product must appear as one product: all request terms in the same item of a list (";" or "," separated),
// not "diesel" in one contract and "generator" in another
const segments = (t: string) => t.split(/[;|\n]|,\s+|\s+-\s+/).map((x) => x.trim()).filter((x) => x.length > 2);
// the product named while a service is bought around it (fuel for generators, servicing of transformers)
const SERVICE_CTX = /\b(maintenance|servicing|service and repair|repairs?|overhaul|demoisturi\w*|installation of|erection|commissioning|fuel for|diesel for|petrol for|hire of|rental of|transport of|inspection of|testing of|calibration of|cleaning of)\b/i;

export function classifyMatch(s: Supplier, conceptTerms: RegExp[][], conceptHs: string[][], query: string, fams = familiesFor(query)): MatchResult {
  const own = `${s.p || ""} ${s.in || ""} ${s.wt || ""}`;        // the company's own words
  const award = `${s.sp || ""}`;                                    // what it supplied under contracts
  const customs = `${s.hd || ""} ${s.cm || ""}`;                    // customs headings and derived commodity names
  const name = String(s.n || "");
  const codes = (String(s.hs || "").replace(/\./g, "").match(/\d{4,6}/g) || []);
  const isService = SERVICE_TYPE.test(String(s.ty || ""));
  const rules = fams.flatMap((f) => f.rules.filter((r) => !r.rx.test(query)));
  const n = conceptTerms.length || 1;
  const all = (seg: string) => conceptTerms.every((t) => t.some((r) => r.test(seg)));
  const conflicts: string[] = [], gaps: string[] = [];
  // stage C per item: an item that names the whole product, with no conflicting product or service context in it
  const judge = (txt: string) => {
    let clean = false, conflicted = "";
    for (const seg of segments(txt)) {
      if (!all(seg)) continue;
      const bad = rules.find((r) => !r.record && r.rx.test(seg));
      if (bad) { if (bad.bucket === "incompatible") conflicted = conflicted || "!" + bad.label; else conflicted = conflicted || bad.label; continue; }
      if (SERVICE_CTX.test(seg)) { conflicted = conflicted || "named in a service or fuel context, not sold"; continue; }
      clean = true;
    }
    return { clean, conflicted };
  };
  const jo = judge(own), ja = judge(award), jc = judge(customs);
  const viaCode = conceptHs.some((hs) => hs.length && codes.some((x) => hs.some((h) => (h.length === 4 ? x.startsWith(h) : x === h))));
  const anywhere = (txt: string) => conceptTerms.filter((t) => t.some((r) => r.test(txt))).length;
  let bucket: Bucket, evidence: string;
  // product text built from shipment records (no site title or industry of its own) names cargo, not a catalogue:
  // a T-shirt print or a forwarder's mixed load can carry the word. It is evidence, not proof.
  const fromShipments = !!(s.hs || s.sh) && !s.wt && !s.in;
  if (jo.clean && !fromShipments) { bucket = "supported"; evidence = "company's own product description"; }
  else if (jo.clean) { bucket = "plausible"; evidence = "shipment records"; gaps.push("named in shipment records; verify that the company makes or sells it"); }
  // a public contract it won names the product, but the winner is often a contractor, installer or distributor
  // (held-out check, 5 Nov 2026: 14 of 27 such "fits" could actually supply, against 17 of 20 from own descriptions)
  else if (ja.clean) { bucket = "plausible"; evidence = "contract items"; gaps.push(isService ? "named in contracts of a works or services firm" : "named in a public contract it won; verify that it makes or sells the product"); }
  else if (jo.conflicted || ja.conflicted) {
    const c = jo.conflicted || ja.conflicted;
    bucket = c.startsWith("!") ? "incompatible" : "related"; evidence = jo.conflicted ? "company's own product description" : "contract items";
    conflicts.push(c.replace(/^!/, ""));
  } else if (jc.clean || viaCode) { bucket = "plausible"; evidence = "customs headings"; gaps.push("only customs codes or headings name the product"); if (jc.conflicted) conflicts.push(jc.conflicted.replace(/^!/, "")); }
  else if (jc.conflicted) { bucket = jc.conflicted.startsWith("!") ? "incompatible" : "related"; evidence = "customs headings"; conflicts.push(jc.conflicted.replace(/^!/, "")); }
  else if (anywhere(`${own} ${award} ${customs}`) >= n) { bucket = "plausible"; evidence = "partial"; gaps.push("the request terms appear separately, not as one product"); }
  else if (anywhere(`${own} ${award} ${customs} ${name}`) >= n) { bucket = "plausible"; evidence = "company name only"; gaps.push("product capability not evidenced (name match)"); }
  else { bucket = "plausible"; evidence = "partial"; gaps.push(`${n - anywhere(`${own} ${award} ${customs}`)} of ${n} product terms not found`); }
  // a wrong product that the company states while not stating the right one (cosmetic urea, rails for PE pipe)
  for (const f of fams) {
    if (f.id === "generic") continue; // generic rules judge the item that names the product, not the whole record
    const ownAward = `${own} ${award}`;
    const right = f.exact ? f.exact.test(f.strip ? ownAward.replace(f.strip, " ") : ownAward) : !!(f.need && f.need.rx.test(ownAward));
    for (const r of f.rules) {
      if (r.rx.test(query) || !r.rx.test(`${own} ${award} ${customs}`)) continue;
      if (!right && r.bucket === "incompatible") { bucket = "incompatible"; conflicts.push(r.label); }
      else if (!right && (bucket === "supported" || bucket === "plausible")) { bucket = "related"; conflicts.push(r.label); }
      else if (!conflicts.includes(r.label)) conflicts.push(`${r.label} (also listed)`);
    }
    if (f.need && bucket === "supported" && !f.need.rx.test(`${own} ${award} ${codes.join(" ")}`)) { bucket = "plausible"; gaps.push(f.need.gap); }
  }
  // a company whose own description is a project role (EPC, PPA, installer) and never says it makes anything
  if (bucket === "supported" && /(?<!for |to |with )\b(epc|turnkey|ppa|installer|installation company)\b(?![\s-]+(contractors?|companies|clients|customers|partners))/i.test(own) && !/\b(manufactur\w*|produc(er|es|tion)|factory|maker|mills?|plant in)\b/i.test(own)) {
    bucket = "related"; conflicts.push("project execution role (installer or EPC)");
  }
  // technical fit before ranking: what the request specifies must be stated by the company's own words or its
  // contract items. Judged on the item that names the product (so "BWRO 8040; SWRO 4040" is not read as SWRO 8040);
  // a requirement that item leaves open is looked for in the rest of the record.
  const reqs = fams.flatMap((f) => (f.specs || []).flatMap((sp) => sp.read(query)));
  let specGap = "";
  if (reqs.length && (bucket === "supported" || bucket === "plausible")) {
    const whole = `${own} ${award}`;
    const run = (txt: string) => reqs.map((r) => r.check(txt));
    const count = (rs: { state: SpecState }[], st: SpecState) => rs.filter((x) => x.state === st).length;
    const wholeRes = run(whole);
    const items = [own, award].flatMap((t) => t.split(/[;|\n]/)).filter((it) => it.trim().length > 2 && all(it))
      .map((it) => run(it).map((x, i) => (x.state === "unstated" ? wholeRes[i] : x)))
      .sort((a, b) => count(a, "conflict") - count(b, "conflict") || count(a, "unstated") - count(b, "unstated"));
    const res = items[0] || wholeRes;
    const bad: string[] = [];
    res.forEach((x, i) => {
      if (x.state === "conflict" && reqs[i].blocking) bad.push(x.note);
      else if (x.state !== "met") { gaps.push(x.note); if (reqs[i].blocking && !specGap) specGap = x.note; }
    });
    if (bad.length) { bucket = "related"; conflicts.unshift(...bad); }
    else if (specGap && bucket === "supported") bucket = "plausible";
    else specGap = "";
  }
  const role = s.td === "yes" || /trader|distributor/i.test(String(s.ty || "")) ? "trader" : /manufactur|producer|goods/i.test(String(s.ty || "")) ? "goods supplier" : "";
  const why = bucket === "supported" ? `Fits because its ${evidence} names ${n > 1 ? "the whole product in one item" : "the product"}`
    : bucket === "plausible" && specGap ? `Possible: its ${evidence} names the product, but a requested specification is not evidenced (${specGap})`
    : bucket === "plausible" ? `Possible: evidence is ${evidence}`
    : bucket === "related" ? `Related, not an exact fit: ${conflicts[0] || "role differs"}`
    : `Not compatible: ${conflicts[0] || ""}`;
  if (!s.web) gaps.push("no website on record");
  if (!role) gaps.push("role (maker or trader) unknown");
  return { bucket, why, evidence, conflicts: [...new Set(conflicts)], gaps };
}

export const BUCKET_RANK: Record<Bucket, number> = { supported: 0, plausible: 1, related: 2, incompatible: 3 };
const EVIDENCE_RANK: Record<string, number> = { "verified on an authoritative source": -1, "company's own product description": 0, "shipment records": 1.5, "own description and contract items": 1, partial: 2, "contract items": 2.5, "customs headings": 3, "company name only": 5, none: 6 };
export const evidenceRank = (e: string) => EVIDENCE_RANK[e] ?? 6;

/** one row per legal entity: same normalised name and country */
export function dedupeKey(s: Supplier): string {
  return `${String(s.n || "").toLowerCase().replace(/\b(co|corp|corporation|inc|ltd|limited|llc|gmbh|sa|s\.a\.|spa|s\.p\.a\.|srl|bv|ag|plc|pte|pvt|private|company|the)\b/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim()}|${s.c || ""}`;
}
