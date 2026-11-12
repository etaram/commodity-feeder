// Supplier matching v2 (lib/matchv2.ts) and the flag MATCH_V2 in the real supplier search (lib/panel.ts).
// Every company and title below is fictional and written for this test; none comes from the evaluation data.
// The network is replaced: the supplier index is a small encrypted file built here, and Google's Decisions API is a
// stub that counts its calls and answers what each case sets. Run: npm test
import { createCipheriv, randomBytes } from "crypto";
import { gzipSync } from "zlib";
import { applyTie, askGeminiForKind, fitRerank, judge, ownFromEvidence, requestRequirement, requirementOf, routeTender, tieToBreak, type Ranked } from "@/lib/matchv2";
import { tenderKind, type TenderKind } from "@/lib/tenderkind";
import { decide, fitInput, kindInput } from "@/lib/gemini";
import { NO_GOODS_NOTE, supplierSearch, type SupQuery } from "@/lib/panel";
let fail = 0;
const ok = (name: string, cond: boolean, got?: unknown) => { if (!cond) fail++; console.log(`${cond ? "ok  " : "FAIL"} ${name}${cond ? "" : " - got " + JSON.stringify(got)}`); };
const labels = (r: { conds: { kind: string; label: string }[] }) => r.conds.map((c) => `${c.kind}:${c.label}`);
const TK = (kind: TenderKind["kind"], confidence: TenderKind["confidence"]): TenderKind => ({ kind, confidence, why: "", goods_phrases: [] });

// ---- A. tender kind routing ----
ok("strong goods: Gemini is not asked", !askGeminiForKind(TK("goods", "high")));
for (const [k, c] of [["non_goods", "high"], ["non_goods", "low"], ["mixed", "high"], ["mixed", "low"], ["goods", "low"], ["unknown", "low"]] as const)
  ok(`${k} ${c}: Gemini is asked`, askGeminiForKind(TK(k, c)));
ok("empty only when both say non_goods", routeTender(TK("non_goods", "high"), "non_goods").block);
ok("rules non_goods, Gemini goods: kept", !routeTender(TK("non_goods", "high"), "goods").block);
ok("rules non_goods, Gemini mixed: kept", !routeTender(TK("non_goods", "high"), "mixed").block);
ok("rules mixed, Gemini non_goods: kept", !routeTender(TK("mixed", "high"), "non_goods").block);
ok("rules non_goods, no Gemini answer: kept", !routeTender(TK("non_goods", "high"), null).block);
ok("rules unknown, Gemini non_goods: kept (the rules never said non_goods)", !routeTender(TK("unknown", "low"), "non_goods").block);

// ---- B. conditions of a request ----
ok("cable request: product, rating, copper, XLPE, power", JSON.stringify(labels(requirementOf("copper power cable XLPE 11 kV"))) === JSON.stringify(["product:cable", "rating:11 kv", "material:copper", "material:xlpe", "form:power"]), labels(requirementOf("copper power cable XLPE 11 kV")));
ok("packaging part gives conditions, no product word", JSON.stringify(labels(requirementOf("RBD palm olein CP10 in 20 litre jerry cans"))) === JSON.stringify(["product:palm olein", "form:refined", "standard:cp10", "rating:20 litre", "form:jerry can"]), labels(requirementOf("RBD palm olein CP10 in 20 litre jerry cans")));
ok("a share takes its word with it", JSON.stringify(labels(requirementOf("granular urea 46% nitrogen"))) === JSON.stringify(["product:urea", "rating:46%", "form:granular"]), labels(requirementOf("granular urea 46% nitrogen")));
ok("a purpose is not a product", JSON.stringify(labels(requirementOf("digital X-ray machine for a hospital"))) === JSON.stringify(["product:xray machine", "form:digital"]), labels(requirementOf("digital X-ray machine for a hospital")));
ok("standard and size code", labels(requirementOf("ductile iron pipe DN300 ISO 2531")).join(",") === "product:pipe,standard:iso 2531,material:ductile iron,standard:dn300", labels(requirementOf("ductile iron pipe DN300 ISO 2531")));
ok("roles and buying words are not product words", labels(requirementOf("fire trucks manufacturer")).join(",") === "product:fire trucks");
ok("several tender phrases: one product condition with alternatives, no spec", (() => { const r = requirementOf("x", ["500 kVA diesel generators", "spare parts"]); return r.conds.length === 1 && r.conds[0].alts!.length === 2; })());
const tk = tenderKind({ title: "Supply and delivery of 500 kVA diesel generators to Northfield hospital" });
ok("a tender is read from its product phrase", labels(requestRequirement("whatever", { kind: tk, title: "t" })).includes("rating:500 kva"), labels(requestRequirement("whatever", { kind: tk, title: "t" })));
ok("a tender without a phrase falls back to its commodity", labels(requestRequirement("t", { kind: TK("unknown", "low"), title: "t", commodity: "maize" })).join(",") === "product:maize");
ok("a tender without phrase or commodity: no condition", requestRequirement("t", { kind: TK("unknown", "low"), title: "t" }).conds.length === 0);

// ---- B. judging rows ----
const cable = requirementOf("copper power cable XLPE 11 kV").conds;
const j1 = judge(cable, { own: "aluminium power cables 11kV, XLPE insulated", kind: "" });
ok("aluminium cable for a copper request: contradicted", j1.contradicted && j1.productProven, j1);
ok("copper and aluminium cables: copper proven, nothing contradicted", (() => { const j = judge(cable, { own: "copper and aluminium power cables, XLPE", kind: "" }); return !j.contradicted && j.proven === 4; })());
ok("an aluminium smelter for a copper cable request: not about cable, so not contradicted", !judge(cable, { own: "aluminium ingots and billets", kind: "" }).contradicted);
ok("customs heading proves the product and the grade", judge(requirementOf("anhydrous ammonia supplier").conds, { own: "Ammonia, anhydrous or in aqueous solution", kind: "" }).proven === 2);
ok("trade synonym: DAP from the customs name", judge(requirementOf("DAP fertilizer 18-46-0").conds, { own: "Diammonium hydrogenorthophosphate (diammonium phosphate)", kind: "" }).productProven);
ok("trade synonym: jet fuel is aviation fuel", judge(requirementOf("Jet A-1 aviation fuel supplier").conds, { own: "jet fuel, diesel", kind: "" }).productProven);
ok("seawater membranes for brackish water: contradicted", judge(requirementOf("reverse osmosis membrane 8040 brackish water").conds, { own: "RO membranes for seawater, 8040", kind: "" }).contradicted);
ok("own words only: the evidence text loses contracts and tags", ownFromEvidence("products: urea | supplied under contracts: cables | customs headings: Urea | commodity tags: fertilizer") === "urea ; Urea");

// ---- B. order, ties ----
type R = { name: string; own: string; kind: string };
const rows: R[] = [
  { name: "trader with cable", own: "power cables copper", kind: "trader" },
  { name: "maker no proof", own: "steel pipes", kind: "maker" },
  { name: "maker with all", own: "copper power cables XLPE 11 kV", kind: "maker" },
  { name: "aluminium only", own: "aluminium power cables", kind: "maker" },
  { name: "maker with cable", own: "power cables copper", kind: "maker" },
];
const rr = fitRerank(rows, cable, (x) => x);
ok("order: most proven, then maker before trader, then the search order; contradiction dropped",
  JSON.stringify(rr.kept.map((x) => x.item.name)) === JSON.stringify(["maker with all", "maker with cable", "trader with cable", "maker no proof"]) && rr.dropped.map((x) => x.item.name).join() === "aluminium only", rr.kept.map((x) => x.item.name));
ok("no condition: the search order stays, makers first", JSON.stringify(fitRerank(rows, [], (x) => x).kept.map((x) => x.was)) === JSON.stringify([1, 2, 3, 4, 0]));
const flat = (n: number, keyOf: (i: number) => string) => Array.from({ length: n }, (_, i) => ({ item: i, j: { states: [], productProven: false, proven: 0, contradicted: false }, key: keyOf(i), was: i })) as Ranked<number>[];
ok("tie of 8 across rank 10: asked", tieToBreak(flat(20, (i) => (i < 6 ? "1:2" : "1:1"))).join(",") === "6,7,8,9,10,11,12,13,14");
ok("tie of 6 inside the top 10: not asked", tieToBreak(flat(20, (i) => (i < 6 ? "1:2" : i < 10 ? "1:1" : "0:0"))).length === 0);
ok("tie of 5 across rank 10: not asked (more than 5 needed)", tieToBreak(flat(20, (i) => (i < 8 ? "1:2" : i < 13 ? "1:1" : "0:0"))).length === 0);
const tied = applyTie(flat(12, (i) => (i < 4 ? "a" : "b")), new Map([[4, "no"], [5, "no"], [6, "yes"], [11, "yes"]]));
ok("tie-break: yes first, then unasked, then no, inside the tie only", JSON.stringify(tied.map((x) => x.item)) === JSON.stringify([0, 1, 2, 3, 6, 11, 7, 8, 9, 10, 4, 5]), tied.map((x) => x.item));

// ---- lib/gemini.ts ----
const fi = fitInput("urea", [{ text: "products: urea" }, { text: "products: cement" }]);
ok("tie-break input: one question per row", Object.keys(fi.questions).join() === "r1,r2" && fi.input.includes("Supplier 2: products: cement"));
ok("tender kind input: the F10 wording", kindInput({ title: "T", sector: "", category: "" }) === "Title: T\nSector: -\nProcurement category: -");

// ---- the flag in the real search ----
const INDEX = [
  { n: "Alucab Wires", c: "TUR", rg: "Europe", tr: "1", q: 90, ty: "manufacturer", s: "Electrical equipment", p: "aluminium power cables 11 kV, overhead conductors", web: "alucab.example" },
  { n: "Cuprum Cables Ltd", c: "IND", rg: "Asia", tr: "2", q: 50, ty: "manufacturer", s: "Electrical equipment", p: "copper power cables XLPE insulated 11 kV 33 kV", web: "cuprum.example" },
  { n: "Generic Cable Trading", c: "ARE", rg: "Middle East", tr: "1", q: 70, ty: "trader", td: "yes", s: "Electrical equipment", p: "power cables, cable trading", web: "gct.example" },
  { n: "Voltaro Gensets Ltd", c: "TUR", rg: "Europe", tr: "1", q: 80, ty: "goods supplier", s: "Energy & power equipment", p: "diesel generators 20-2000 kVA, alternators", web: "voltaro.example" },
  { n: "Aquaflow Pumps GmbH", c: "DEU", rg: "Europe", tr: "1", q: 75, ty: "goods supplier", s: "Water & sanitation", p: "water pumps, water supply system components, valves", web: "aquaflow.example" },
];
const key = randomBytes(32), nonce = randomBytes(12), c = createCipheriv("aes-256-gcm", key, nonce);
const body = Buffer.concat([c.update(gzipSync(Buffer.from(JSON.stringify(INDEX)))), c.final()]);
const file = Buffer.concat([nonce, body, c.getAuthTag()]);
process.env.WEB_INDEX_KEY = key.toString("base64");
for (const k of ["ANTHROPIC_API_KEY", "GOOGLE_SERVICE_ACCOUNT_JSON", "TENDER_KIND", "MATCH_V2", "GEMINI_API_KEY"]) delete process.env[k];
let google = 0, kindAnswer = "non_goods", sentKey = "";
globalThis.fetch = (async (url: unknown, init?: RequestInit) => {
  if (/decisions$/.test(String(url))) {
    google++; sentKey = String((init?.headers as Record<string, string>)["x-goog-api-key"] || "");
    const qs = JSON.parse(String(init?.body)).questions as Record<string, unknown>;
    return new Response(JSON.stringify({ answers: Object.fromEntries(Object.keys(qs).map((k) => [k, { choice: k === "kind" ? kindAnswer : "yes" }])) }));
  }
  return /suppliers\.enc$/.test(String(url)) ? new Response(file) : new Response("", { status: 404 });
}) as typeof fetch;
for (const k of ["log", "info", "warn", "error"] as const) { const say = console[k]; console[k] = (...a: unknown[]) => { if (/^(ok  |FAIL)/.test(String(a[0]))) say(...a); }; }
const names = (r: { values: string[][] }) => r.values.slice(1).map((x) => x[r.values[0].indexOf("supplier")]);
const product: SupQuery = { text: "copper power cable XLPE 11 kV", n: 15, strict: false, noExpand: true };
const worksTitle = "Rehabilitation of the water supply system of Northfield town";
const tender = (title: string): SupQuery => ({ sector: "", text: `${title} `, country: "", region: "", hs: "", n: 15, tender: { title, category: "" } });

(async () => {
  const off1 = await supplierSearch(product);
  for (const flag of [undefined, "off", "ON", "1"]) {
    if (flag === undefined) delete process.env.MATCH_V2; else process.env.MATCH_V2 = flag;
    ok(`MATCH_V2 ${JSON.stringify(flag)}: the search answers as before`, JSON.stringify(await supplierSearch(product)) === JSON.stringify(off1) && !("match_v2" in off1));
  }
  ok("flag off: the aluminium cable maker is in the list", names(off1).includes("Alucab Wires"), names(off1));
  delete process.env.MATCH_V2;
  const offWorks = await supplierSearch(tender(worksTitle));
  process.env.MATCH_V2 = "on";
  const on1 = await supplierSearch(product);
  ok("flag on: the aluminium-only maker is dropped, the copper XLPE maker leads", !names(on1).includes("Alucab Wires") && names(on1)[0] === "Cuprum Cables Ltd" && on1.total === off1.total - 1, names(on1));
  ok("flag on, no key: Google is never called", google === 0);
  const noKey = await supplierSearch(tender(worksTitle));
  ok("flag on, no key: a works tender keeps its list (one opinion is not enough)", noKey.values.length === offWorks.values.length && !noKey.note, names(noKey));
  process.env.GEMINI_API_KEY = "test-key-123";
  kindAnswer = "goods";
  const disagree = await supplierSearch(tender(worksTitle));
  ok("rules non_goods, Gemini goods: the list is kept", !disagree.note && disagree.values.length > 1 && google === 1, { google, n: disagree.values.length });
  ok("the key travels in the header", sentKey === "test-key-123");
  await supplierSearch(tender(worksTitle));
  ok("the same tender is not asked twice", google === 1, google);
  kindAnswer = "non_goods";
  const both = await supplierSearch(tender(worksTitle + " phase two"));
  ok("rules and Gemini both non_goods: empty list with the note", both.values.length === 1 && both.note === NO_GOODS_NOTE && both.total === 0 && google === 2, both);
  const goods = await supplierSearch(tender("Supply of copper power cables XLPE 11 kV"));
  ok("a strong goods tender: Gemini not asked, list kept", google === 2 && names(goods).includes("Cuprum Cables Ltd") && !goods.note, names(goods));
  delete process.env.MATCH_V2; delete process.env.GEMINI_API_KEY;
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.log(`FAIL the search ran - got ${String(e).slice(0, 300)}`); process.exit(1); });
void decide;
