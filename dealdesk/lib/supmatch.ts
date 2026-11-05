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
// The company name locates an entity; it never establishes product capability. HS/CPV codes are retrieval
// signals, not proof of compatibility. Terms match on whole words ("corn" is not in "Corning").
export const MATCH_VERSION = "match-1 (2026-11-05)";
export type Bucket = "supported" | "plausible" | "related" | "incompatible";
export type MatchResult = { bucket: Bucket; why: string; evidence: string; conflicts: string[]; gaps: string[] };

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** whole-word (or whole-phrase) match; a trailing plural s/es is allowed, a longer word is not */
export function termRe(term: string): RegExp {
  const t = term.toLowerCase().trim().replace(/\s+/g, " ");
  const base = t.length > 4 && t.endsWith("s") && !t.endsWith("ss") ? t.slice(0, -1) : t;
  const body = base.split(" ").map(esc).join("[\\s\\-]+");
  return new RegExp(`(^|[^\\p{L}\\p{N}])${body}(e?s)?(?=$|[^\\p{L}\\p{N}])`, "iu");
}

type Rule = { rx: RegExp; label: string; bucket: "related" | "incompatible" };
// exact: the right product stated outright; strip: phrases removed before that test (in "maize flour" the word
// maize names flour, not grain)
type Family = { id: string; when: RegExp; need?: { rx: RegExp; gap: string }; exact?: RegExp; strip?: RegExp; rules: Rule[] };
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
      { rx: /\b(urea[- ]formaldehyde|resins?|adhesives?|glue)\b/i, label: "urea resin or adhesive", bucket: "related" },
      { rx: /\b(adblue|def\b|diesel exhaust fluid)\b/i, label: "automotive urea solution", bucket: "related" },
    ] },
  { id: "maize", when: /\b(maize|corn)\b/i,
    exact: /\b(maize|corn)\b/i, strip: /\b(maize|corn)[\s-]+(flour|meal|starch|syrup|gluten|bran|oil|flakes|grits|snacks?|chips|feed|silage)\b|\b(sweet ?corn|popcorn|corn ?flakes)\b/gi,
    need: { rx: /\b(maize|corn)\b/i, gap: "maize not named in the company's own products" },
    rules: [
      { rx: /\b(flour|meal|starch|snacks?|chips|syrup|gluten|bran|popcorn|tortillas?|sweet ?corn|canned|corn oil|cornflakes?|grits|dextrose)\b/i, label: "processed maize product, not whole grain", bucket: "related" },
      { rx: /\b(animal feed|feed mill|silage|ddgs|by-?products?)\b/i, label: "feed or by-product", bucket: "related" },
    ] },
  { id: "generator", when: /\b(generators?|gensets?|generating sets?)\b/i,
    rules: [
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
];

export function familiesFor(query: string): Family[] {
  return FAMILIES.filter((f) => f.when.test(query));
}

const SERVICE_TYPE = /services/i;

export function classifyMatch(s: Supplier, conceptTerms: RegExp[][], conceptHs: string[][], query: string, fams = familiesFor(query)): MatchResult {
  const own = `${s.p || ""} ${s.in || ""} ${s.wt || ""}`.toLowerCase();      // the company's own words
  const award = `${s.sp || ""} ${s.cm || ""}`.toLowerCase();                  // what it supplied under contracts
  const customs = `${s.hd || ""}`.toLowerCase();                              // customs headings (from codes)
  const name = String(s.n || "").toLowerCase();
  const codes = (String(s.hs || "").replace(/\./g, "").match(/\d{4,6}/g) || []);
  let inOwn = 0, inAward = 0, inCustoms = 0, inName = 0;
  for (let i = 0; i < conceptTerms.length; i++) {
    const t = conceptTerms[i], hs = conceptHs[i] || [];
    const viaCode = codes.length > 0 && hs.some((h) => codes.some((x) => (h.length === 4 ? x.startsWith(h) : x === h)));
    if (t.some((r) => r.test(own))) inOwn++;
    else if (t.some((r) => r.test(award))) inAward++;
    else if (viaCode || t.some((r) => r.test(customs))) inCustoms++;
    else if (t.some((r) => r.test(name))) inName++;
  }
  const n = conceptTerms.length || 1, found = inOwn + inAward + inCustoms + inName;
  const conflicts: string[] = [], gaps: string[] = [];
  const evidenceText = `${own} ${award} ${customs}`;
  let bucket: Bucket;
  let evidence = inOwn === n ? "company's own product description" : inOwn + inAward === n ? "own description and contract items"
    : inOwn + inAward + inCustoms === n ? (inCustoms ? "customs headings" : "contract items") : found ? "partial" : "none";
  if (found < n) { bucket = "plausible"; gaps.push(`${n - found} of ${n} product terms not found`); }
  else if (inName && inOwn + inAward + inCustoms < n) { bucket = "plausible"; evidence = "company name only"; gaps.push("product capability not evidenced (name match)"); }
  else if (inOwn === n || (inOwn + inAward === n && !SERVICE_TYPE.test(String(s.ty || "")))) bucket = "supported";
  else { bucket = "plausible"; gaps.push(inCustoms ? "only customs codes or headings name the product" : "named only in contracts it delivered as services"); }
  if (inAward && !inOwn && SERVICE_TYPE.test(String(s.ty || "")) && bucket !== "plausible") { bucket = "related"; conflicts.push("supplied within service contracts"); }
  for (const f of fams) {
    for (const r of f.rules) {
      if (r.rx.test(query)) continue; // the buyer asked for that product itself
      if (!r.rx.test(evidenceText)) continue;
      // a rule about the wrong product only applies when the right one is not also stated
      const right = f.exact ? f.exact.test(f.strip ? own.replace(f.strip, " ") : own) : !!(f.need && f.need.rx.test(own));
      if (r.bucket === "incompatible" && !right) { bucket = "incompatible"; conflicts.push(r.label); }
      else if (!right && bucket !== "incompatible") { if (bucket === "supported" || bucket === "plausible") bucket = "related"; conflicts.push(r.label); }
      else conflicts.push(`${r.label} (also listed)`);
    }
    if (f.need && !f.need.rx.test(`${own} ${award}`) && !(codes.length && f.need.rx.test(codes.join(" "))) && bucket === "supported") { bucket = "plausible"; gaps.push(f.need.gap); }
  }
  const role = s.td === "yes" || /trader|distributor/i.test(String(s.ty || "")) ? "trader" : /manufactur|producer|goods/i.test(String(s.ty || "")) ? "goods supplier" : "";
  const why = bucket === "supported" ? `Fits because its ${evidence} names ${conceptTerms.length > 1 ? "every part of the request" : "the product"}`
    : bucket === "plausible" ? `Possible: evidence is ${evidence}`
    : bucket === "related" ? `Related, not an exact fit: ${conflicts[0] || "role differs"}`
    : `Not compatible: ${conflicts[0] || ""}`;
  if (!s.web) gaps.push("no website on record");
  if (!role) gaps.push("role (maker or trader) unknown");
  return { bucket, why, evidence, conflicts: [...new Set(conflicts)], gaps };
}

export const BUCKET_RANK: Record<Bucket, number> = { supported: 0, plausible: 1, related: 2, incompatible: 3 };
const EVIDENCE_RANK: Record<string, number> = { "company's own product description": 0, "own description and contract items": 1, "contract items": 2, "customs headings": 3, partial: 4, "company name only": 5, none: 6 };
export const evidenceRank = (e: string) => EVIDENCE_RANK[e] ?? 6;

/** one row per legal entity: same normalised name and country */
export function dedupeKey(s: Supplier): string {
  return `${String(s.n || "").toLowerCase().replace(/\b(co|corp|corporation|inc|ltd|limited|llc|gmbh|sa|s\.a\.|spa|s\.p\.a\.|srl|bv|ag|plc|pte|pvt|private|company|the)\b/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim()}|${s.c || ""}`;
}
