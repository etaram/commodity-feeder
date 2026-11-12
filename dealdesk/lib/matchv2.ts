// Supplier matching v2, behind the flag MATCH_V2 (default off). Two changes on top of the search of lib/panel.ts,
// both working on the rows the search already retrieved (nothing is retrieved again):
//
//   A. tender kind routing. The rules of lib/tenderkind.ts read the tender first. Only a strong goods reading (goods,
//      high confidence) is trusted alone; in every other case (non_goods, mixed, or unsure = neither a strong goods
//      nor a strong service reading) Google's gemini-decision-1 is asked the closed-choice question of benchmark F10.
//      The supplier list is emptied only when BOTH say non_goods. Why both: emptying a goods tender is the costly
//      mistake (the user gets nothing to quote), and the two fail on different tenders (F10: the rules emptied one
//      goods tender that Gemini read right; Gemini caught every non_goods tender the rules caught).
//   B. supplier fit. The request is split by code into mandatory conditions: the product, and each material or
//      grade, standard or code, form or packaging, and rating it states. Each candidate row is judged per condition
//      from its own fields (products, industries, site title, customs headings; never the company name and never
//      the contracts it once won): proven, contradicted or missing. A row that contradicts a stated condition about
//      the same product (aluminium cable for a copper request, seawater membranes for brackish water) is dropped.
//      Order: product proven first, then more proven conditions, then maker before trader, then the search's own order.
//      Where that still leaves a wide tie that straddles the first screen (more than 5 rows of equal proof among the
//      top 15, and the tie crosses rank 10), Gemini may break it with one yes/no question per row, all rows of the
//      request in one call (lib/gemini.ts fitInput); "yes" goes before "no" inside the tie, nothing is dropped by it.
//
// Pure functions only (no I/O); the network part is the caller's (lib/panel.ts, tools/eval-matchv2.ts).
import { fold, type TenderKind } from "@/lib/tenderkind";

// ---------------------------------------------------------------- A. tender kind routing
export type Kind3 = "goods" | "non_goods" | "mixed";
/** a strong goods reading: the only verdict of the rules that is trusted without a second opinion */
export const strongGoods = (k: TenderKind) => k.kind === "goods" && k.confidence === "high";
/** a strong service or works reading */
export const strongService = (k: TenderKind) => k.kind === "non_goods" && k.confidence === "high";
/** unsure: the rules found neither a strong goods phrase nor a strong service phrase */
export const unsure = (k: TenderKind) => !strongGoods(k) && !strongService(k);
/** Gemini is asked when the rules say non_goods or mixed, or are unsure */
export const askGeminiForKind = (k: TenderKind) => k.kind === "non_goods" || k.kind === "mixed" || unsure(k);
export type Route = { block: boolean; rules: TenderKind["kind"]; gemini: Kind3 | null; why: string };
/** gemini: its answer, or null when it was not asked or did not answer (then the list is always kept) */
export function routeTender(k: TenderKind, gemini: Kind3 | null): Route {
  const block = k.kind === "non_goods" && gemini === "non_goods";
  const why = block ? "the rules and Gemini both read a tender that buys no goods"
    : !askGeminiForKind(k) ? "the rules read a clear goods purchase"
    : gemini === null ? "no second opinion available: the supplier list is kept"
    : k.kind === "non_goods" ? `the rules read no goods but Gemini reads ${gemini}: the supplier list is kept`
    : `the rules read ${k.kind}${k.confidence === "low" ? " (unsure)" : ""}: the supplier list is kept`;
  return { block, rules: k.kind, gemini, why };
}

// ---------------------------------------------------------------- B. conditions of a request
export type CondKind = "product" | "material" | "standard" | "form" | "rating";
export type Cond = { kind: CondKind; label: string;
  /** product only: alternative word sets; an alternative is proven when its required words are present (one may be
   *  missing when it has three or more) */
  alts?: { req: string[]; opt: string[] }[];
  /** other kinds: proven when this matches the row's own text */
  re?: RegExp;
  /** a value that excludes this one (aluminium for copper); counts only where the row also names the product */
  opposite?: RegExp };
export type State = "proven" | "missing" | "contradicted";

/** The row text and the request text are read the same way: folded, spelling variants unified; the row text also
 *  gets trade synonyms written out in one canonical form next to its words (so "jet fuel" also reads as "aviation
 *  fuel"). The lists are generic trade vocabulary.
 *  spelling variants, replaced in place in the request and in the row alike */
const SPELL: [RegExp, string][] = [
  [/\bgen(?:erating)?[- ]?sets?\b|\bgensets?\b/g, "generator"], [/\bfertilis/g, "fertiliz"], [/\baluminum\b/g, "aluminium"], [/\btyres?\b/g, "tire"],
  [/\bx[- ]?rays?\b/g, "xray"], [/\bsulphur/g, "sulfur"], [/\bcentre\b/g, "center"], [/\bcontaineris/g, "containeriz"],
];
const ALIASES: [RegExp, string][] = [
  [/\bro\b/g, "reverse osmosis"],
  [/\bdi-?ammonium (?:hydrogen ?ortho)?phosphates?\b|\bdiammonium hydrogenorthophosphate\b/g, "dap"],
  [/\bliquefied petroleum gas(?:es)?\b|\bliquified petroleum gas\b|\bpropane\b|\bbutane\b|\bautogas\b/g, "lpg"],
  [/\bjet[- ]?fuels?\b|\baviation turbine fuels?\b|\baviation kerosene\b|\bkerosene(?:-type)?\b|\bjet[- ]?a-?1\b|\bavtur\b/g, "aviation fuel"],
  [/\buninterruptible power (?:supply|supplies|systems?|sources?)\b/g, "ups"],
  [/\bradiograph\w*|\bradiolog\w*/g, "xray"],
  [/\bfire[- ]?fighting (?:vehicles?|trucks?|engines?)\b|\bfire (?:engines?|tenders?|apparatus)\b|\bfire-trucks?\b/g, "fire truck"],
  [/\bvital[- ]signs? monitors?\b|\bmulti-?parameter (?:patient )?monitors?\b|\bpatient monitoring\b/g, "patient monitor"],
  [/\bliquid (?:supply or production )?meters?\b|\bwater flow meters?\b/g, "water meter"],
  [/\bpalm oil\b|\bpalm fractions?\b/g, "palm olein"],
  [/\bsunflower[- ]seed\b/g, "sunflower"],
  [/\bphotovoltaic\b|\bpv modules?\b|\bsolar modules?\b/g, "solar panel"],
  [/\breinforc\w* (?:steel )?bars?\b|\btmt bars?\b/g, "rebar"],
];
const spell = (text: string) => {
  let t = fold(String(text || "")).replace(/[\u2010-\u2015]/g, "-").replace(/\s+/g, " ").trim();
  for (const [re, to] of SPELL) t = t.replace(re, to);
  return t;
};
export function canon(text: string): string {
  const t = spell(text), extra: string[] = [];
  for (const [re, to] of ALIASES) { re.lastIndex = 0; if (re.test(t)) extra.push(to); re.lastIndex = 0; }
  return extra.length ? `${t} ${extra.join(" ")}` : t;
}
/** a word and its plural share one stem; "x-ray" and "xray" are one word */
export const stem = (w: string) => {
  let s = w.replace(/-/g, "");
  if (s.length > 4 && s.endsWith("ies")) s = s.slice(0, -3) + "y";
  else if (s.length > 4 && /(?:ches|shes|sses|xes)$/.test(s)) s = s.slice(0, -2);
  else if (s.length > 3 && s.endsWith("s") && !s.endsWith("ss")) s = s.slice(0, -1);
  return s;
};
const wordsOf = (t: string) => t.split(/[^a-z0-9\-]+/).map((w) => w.replace(/^-+|-+$/g, "")).filter(Boolean);
const stemsOf = (t: string) => new Set(wordsOf(t).map(stem));

// material, grade, form and packaging words: each one stated in a request is a condition of its own (not a product
// word). [label, kind, pattern, opposite or ""]. Opposites are only for values that exclude each other on one product.
const LEX: [string, CondKind, string, string][] = [
  ["copper", "material", "copper", "aluminium(?! and copper)"],
  ["aluminium", "material", "aluminium", "copper(?! and aluminium)"],
  ["xlpe", "material", "xlpe|cross[- ]?linked polyethylene", ""],
  ["hdpe", "material", "hdpe|high[- ]density polyethylene|polyethylene|pe ?100|pe ?80", "u?pvc|ductile iron|cast iron|grp"],
  ["upvc", "material", "u?pvc", "hdpe|polyethylene|ductile iron"],
  ["ductile iron", "material", "ductile(?: cast)? iron", "u?pvc|hdpe|polyethylene|grp"],
  ["stainless", "material", "stainless", ""],
  ["galvanized", "material", "galvani[sz]ed", ""],
  ["lithium", "material", "lithium|li-?ion|lifepo4|lfp", "lead[- ]acid"],
  ["latex", "material", "latex", "nitrile(?! and latex)|vinyl"],
  ["nitrile", "material", "nitrile", "latex(?! and nitrile)|vinyl"],
  ["monocrystalline", "material", "mono[- ]?crystalline|mono[- ]?perc|mono[- ]?si", "poly[- ]?crystalline|thin[- ]film|amorphous"],
  ["polycrystalline", "material", "poly[- ]?crystalline", "mono[- ]?crystalline"],
  ["refined", "form", "refined|refinery|refining|rbd", "crude"],
  ["anhydrous", "form", "anhydrous", ""],
  ["granular", "form", "granul(?:ar|ated)", "prill(?:ed|s)?"],
  ["prilled", "form", "prill(?:ed|s)?", "granul(?:ar|ated)"],
  ["brackish", "form", "brackish(?: water)?|low[- ]energy|bw ?30", "sea ?water|swro|sw ?30"],
  ["seawater", "form", "sea ?water|swro|sw ?30", "brackish|bw ?30"],
  ["containerized", "form", "containeri[sz]ed|container(?:i[sz]ed)? (?:plants?|systems?|units?)|skid[- ]?mounted|mobile (?:plants?|units?)", ""],
  ["online", "form", "on[- ]?line|double[- ]conversion", "off[- ]?line|line[- ]interactive"],
  ["crawler", "form", "crawler|tracked", "wheeled"],
  ["digital", "form", "digital|flat[- ]panel|dr systems?", "analog(?:ue)?"],
  ["diesel", "form", "diesel", "gas[- ](?:fired|engine)s?|natural gas|biogas|petrol|gasoline"],
  ["power", "form", "power", ""],
  ["distribution", "form", "distribution", ""],
  ["bulk", "form", "bulk", ""],
  ["jerry can", "form", "jerry ?cans?|jerrycans?|plastic cans?|pet bottles?|bottled", "flexi ?tanks?|isotanks?"],
  ["cold water", "form", "cold", ""],
  ["hot rolled", "form", "hot[- ]rolled", "cold[- ]rolled(?! and hot)"],
  ["cold rolled", "form", "cold[- ]rolled", "hot[- ]rolled(?! and cold)"],
  ["white", "form", "white", "yellow(?! and white)"],
  ["yellow", "form", "yellow", "white(?! and yellow)"],
  ["long grain", "form", "long[- ]grain", ""],
  ["sterile", "form", "sterile|sterili[sz]ed", ""],
  ["deformed", "form", "deformed|ribbed|tmt", ""],
  ["milling", "form", "milling", "feed (?:wheat|grade)"],
  ["edible", "form", "edible|cooking|food[- ]grade", ""],
  ["intensive care", "form", "intensive care|icu|critical care", ""],
  ["penetration grade", "form", "penetration(?: grade)?", ""],
  ["desalination", "form", "desalination|desalting|desalinat\\w*", ""],
];
const LEX_RX = LEX.map(([label, kind, p, opp]) => ({ label, kind, re: new RegExp(`(?<![a-z0-9])(?:${p})(?![a-z0-9])`), opp: opp ? new RegExp(`(?<![a-z0-9])(?:${opp})(?![a-z0-9])`) : undefined }));
// named standards and grade codes ("ISO 2531", "ICUMSA 45", "CEM I 42.5N", "Jet A-1")
const STD_RX = /(?<![a-z0-9])(?:(?:iso|en|astm|iec|bs|din|api|asme|sans|nfpa|awwa|icumsa|is|ks|gost|jis)\s?-?\d[\da-z.\-:/]*|cem\s?[iv]{1,3}(?:\/[ab])?\s?\d{2}(?:[.,]5)?\s?[nr]?|jet\s?a-?1)(?![a-z0-9])/g;
// a stated quantity with a unit: "500 kVA", "132/33 kV", "20 ton", "110 mm", "42U", "20 litre"
const UNIT = "kva|mva|kv|kw|mw|mwh|kwh|wp|w|mm|cm|ton(?:ne)?s?|t|u|l|litres?|liters?|hz|bar|psi|inch(?:es)?|ah|gsm|mt";
const RATING_RX = new RegExp(`(?<![a-z0-9.])(\\d+(?:[.,]\\d+)?(?:\\/\\d+(?:[.,]\\d+)?)?)\\s?(${UNIT})(?![a-z0-9])`, "g");
// a share with what it measures: "46% nitrogen", "12.5% protein", "5% broken" (the word after it is not a product word)
const PCT_RX = /(?<![a-z0-9.])(\d+(?:[.,]\d+)?)\s?%(?:\s+(?:of\s+)?[a-z]+)?/g;
// words that never name the product: roles, buying words, fillers
const STOP = new Set(("supplier suppliers manufacturer manufacturers maker makers producer producers exporter exporters distributor distributors " +
  "dealer dealers vendor vendors trader traders supply supplies supplying delivery purchase procurement provision buy buying " +
  "of and or the a an with from by to in on at as per new high premium quality grade type best good standard various other " +
  "human consumption use used item items lot lots no number").split(" "));
// class words: they say what kind of thing the product is, not which; optional when another product word is stated
const CLASS = new Set(("machine machines system systems unit units equipment equipments plant plants set sets device devices apparatus product products " +
  "fertilizer fertilizers material materials kit kits solution solutions goods article articles").split(" "));
const PURPOSE_RX = /\s(?:for|to be used|intended for|destined|at|under)\s.*$/;
const PACK_RX = /\s(?:in|packed in|packaged in)\s+(?=\d|bulk|bags?|drums?|jerry|cartons?|bottles?|containers?|flexi)/;

export type Requirement = { conds: Cond[]; product: string };
/** the conditions one request states. For a tender, pass the product phrases the rules found (lib/tenderkind.ts):
 *  several phrases are several products bought, any of which a supplier may cover, so only the product is a condition */
export function requirementOf(text: string, phrases?: string[]): Requirement {
  const list = (phrases && phrases.length ? phrases : [text]).map((p) => String(p || "").trim()).filter(Boolean);
  if (!list.length) return { conds: [], product: "" };
  const parsed = list.map(parsePhrase);
  const alts = parsed.map((p) => p.alt).filter((a) => a.req.length || a.opt.length).map((a) => (a.req.length ? a : { req: a.opt, opt: [] }));
  const conds: Cond[] = [];
  if (alts.length) conds.push({ kind: "product", label: parsed.filter((p) => p.alt.req.length || p.alt.opt.length).map((p) => p.words).join(" / "), alts });
  if (parsed.length === 1) conds.push(...parsed[0].specs);
  return { conds, product: list.join(", ").slice(0, 120) };
}
function parsePhrase(raw: string): { alt: { req: string[]; opt: string[] }; specs: Cond[]; words: string } {
  let t = spell(raw);
  const specs: Cond[] = [], seen = new Set<string>();
  const add = (c: Cond) => { if (!seen.has(c.label)) { seen.add(c.label); specs.push(c); } };
  // the packaging part ("in 20 litre jerry cans") gives conditions but no product word; the purpose ("for a
  // hospital") is dropped
  const pk = PACK_RX.exec(t); let tail = "";
  if (pk) { tail = t.slice(pk.index); t = t.slice(0, pk.index); }
  t = t.replace(PURPOSE_RX, " ");
  const strip = (part: string) => {
    let all = part.replace(STD_RX, (m) => { const k = m.replace(/\s+/g, " ").trim(); add({ kind: "standard", label: k, re: new RegExp(`(?<![a-z0-9])${looseRx(k)}(?![a-z0-9])`) }); return " "; });
    all = all.replace(PCT_RX, (_m, n: string) => { const v = n.replace(",", "."); add({ kind: "rating", label: `${v}%`, re: new RegExp(`(?<![0-9.])${esc(v)}\\s?%`) }); return " "; });
    all = all.replace(RATING_RX, (_m, n: string, u: string) => {
      const v = n.replace(",", "."), unit = u.replace(/s$/, "");
      add({ kind: "rating", label: `${v} ${unit}`, re: new RegExp(`(?<![0-9.])${v.split("/").map(esc).join("\\s?\\/\\s?")}\\s?${esc(unit)}s?(?![a-z])`) });
      return " ";
    });
    // a grade written as two numbers ("60/70" penetration) is one code
    all = all.replace(/(?<![a-z0-9.\/])\d+(?:\/\d+)+(?![a-z0-9.\/])/g, (m) => { add({ kind: "standard", label: m, re: new RegExp(`(?<![0-9])${m.split("/").map(esc).join("\\s?\\/\\s?")}(?![0-9])`) }); return " "; });
    for (const x of LEX_RX) {
      if (!x.re.test(all)) continue;
      add({ kind: x.kind, label: x.label, re: x.re, opposite: x.opp });
      all = all.replace(new RegExp(x.re.source, "g"), " ");
    }
    // any other token with a digit is a model, size or grade code ("8040", "CP10", "B500B", "PN16", "DN300", "18-46-0")
    for (const w of wordsOf(all)) if (/\d/.test(w) && w.length >= 2) {
      add({ kind: "standard", label: w, re: new RegExp(`(?<![a-z0-9])${looseRx(w)}(?![a-z0-9])`) });
      all = all.replace(w, " ");
    }
    return all;
  };
  const rest = strip(t);
  strip(tail);
  const ws = wordsOf(rest).filter((w) => !/\d/.test(w) && w.length >= 2 && !STOP.has(w));
  const req = [...new Set(ws.filter((w) => !CLASS.has(w)).map(stem))].slice(0, 6), opt = [...new Set(ws.filter((w) => CLASS.has(w)).map(stem))];
  return { alt: { req, opt }, specs, words: ws.join(" ") };
}
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** "iso 2531" also reads "ISO2531" and "ISO-2531"; "18-46-0" also "18 46 0" */
const looseRx = (k: string) => k.split(/[\s\-]+/).filter(Boolean).map(esc).join("[\\s\\-]?");
// ---------------------------------------------------------------- B. judging one row
export type FitRow = {
  /** the company's own words: products, industries, site title, customs headings */
  own: string;
  /** "maker", "trader" or "" (lib/panel.ts supplierKind) */
  kind: string;
};
/** the own words inside an evidence text as lib/evalrows.ts evidenceText writes it ("products: x | industries: y |
 *  site title: z | supplied under contracts: ... | customs headings: ..."): contracts and derived tags are left out */
export function ownFromEvidence(evidence: string): string {
  return String(evidence || "").split(" | ").filter((p) => /^(products|industries|site title|customs headings):/.test(p)).map((p) => p.replace(/^[a-z ]+:\s*/, "")).join(" ; ");
}
export type Judged = { states: State[]; productProven: boolean; proven: number; contradicted: boolean };
export function judge(conds: Cond[], row: FitRow): Judged {
  const t = canon(row.own), stems = stemsOf(t);
  const has = (w: string) => stems.has(w);
  const p = conds.find((c) => c.kind === "product");
  const productProven = !!p && (p.alts || []).some((a) => {
    const got = a.req.filter(has).length;
    return a.req.length > 0 && got >= (a.req.length >= 3 ? a.req.length - 1 : a.req.length);
  });
  const states = conds.map((c): State => {
    if (c.kind === "product") return productProven ? "proven" : "missing";
    if (c.re && c.re.test(t)) return "proven";
    // a stated value excluded by the row counts only where the row is about the same product
    if (c.opposite && productProven && c.opposite.test(t)) return "contradicted";
    return "missing";
  });
  return { states, productProven, proven: states.filter((s) => s === "proven").length, contradicted: states.includes("contradicted") };
}

const KIND_RANK: Record<string, number> = { maker: 0, "": 1, trader: 2 };
export type Ranked<T> = { item: T; j: Judged; key: string; was: number; tie?: "yes" | "no" };
/** drop contradicted rows, then order: product proven, more proven, maker before trader, the search's own order */
export function fitRerank<T>(items: T[], conds: Cond[], toRow: (x: T) => FitRow): { kept: Ranked<T>[]; dropped: Ranked<T>[] } {
  const all = items.map((item, was) => { const j = judge(conds, toRow(item)); return { item, j, key: `${j.productProven ? 1 : 0}:${j.proven}`, was, kind: toRow(item).kind }; });
  const kept = all.filter((x) => !x.j.contradicted), dropped = all.filter((x) => x.j.contradicted);
  kept.sort((a, b) => Number(b.j.productProven) - Number(a.j.productProven) || b.j.proven - a.j.proven
    || (KIND_RANK[a.kind] ?? 1) - (KIND_RANK[b.kind] ?? 1) || a.was - b.was);
  return { kept: kept.map(({ kind: _k, ...x }) => x), dropped: dropped.map(({ kind: _k, ...x }) => x) };
}

/** Is a Gemini tie-break worth one call? More than 5 rows of equal proof among the top 15, and that tie crosses rank
 *  10 (only then does the answer change which rows the first screen shows). Returns the positions (0-based, in the
 *  top 15) to ask about, or [] for no call. */
export function tieToBreak<T>(kept: Ranked<T>[], top = 15, minTie = 5, screen = 10): number[] {
  const head = kept.slice(0, top), count = new Map<string, number>();
  for (const x of head) count.set(x.key, (count.get(x.key) || 0) + 1);
  const wide = [...count.entries()].filter(([, n]) => n > minTie).map(([k]) => k);
  const crossing = wide.filter((k) => { const pos = head.map((x, i) => (x.key === k ? i : -1)).filter((i) => i >= 0); return pos[0] < screen && pos[pos.length - 1] >= screen; });
  return crossing.length ? head.map((x, i) => (crossing.includes(x.key) ? i : -1)).filter((i) => i >= 0) : [];
}
/** apply the yes/no answers inside each tie: "yes" first, then no answer, then "no"; other rows keep their places */
export function applyTie<T>(kept: Ranked<T>[], answers: Map<number, "yes" | "no">): Ranked<T>[] {
  const out = kept.map((x, i) => ({ ...x, tie: answers.get(i) }));
  const order = (x: Ranked<T>) => (x.tie === "yes" ? 0 : x.tie === "no" ? 2 : 1);
  const slots = new Map<string, number[]>();
  out.forEach((x, i) => { if (answers.has(i)) slots.set(x.key, [...(slots.get(x.key) || []), i]); });
  const res = [...out];
  for (const pos of slots.values()) {
    const group = pos.map((i) => out[i]).sort((a, b) => order(a) - order(b) || a.was - b.was);
    pos.forEach((p, k) => { res[p] = group[k]; });
  }
  return res;
}
