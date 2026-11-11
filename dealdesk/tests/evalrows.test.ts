// The blind supplier-match evaluation: the request set, the labeller's rows (no verdict in them) and the tender sample.
// Fictional companies only. Run: npm test
import { EVAL_SET, QUERIES } from "@/lib/evalqueries";
import { BLIND_KEYS, EVIDENCE_MAX, evidenceText, pickTenders, splitResults, stratumOf, summarize, tenderRequest } from "@/lib/evalrows";
import { queryWords, plainConceptWords } from "@/lib/panel";
import { SERVICE_SECTOR } from "@/lib/supfit";
let fail = 0;
const ok = (name: string, cond: boolean, got?: unknown) => { if (!cond) fail++; console.log(`${cond ? "ok  " : "FAIL"} ${name}${cond ? "" : " - got " + JSON.stringify(got)}`); };

// the request set
ok("40 requests", EVAL_SET.length === 40, EVAL_SET.length);
ok("ids are unique Q01..Q40", new Set(EVAL_SET.map((q) => q.id)).size === 40 && EVAL_SET.every((q, i) => q.id === `Q${String(i + 1).padStart(2, "0")}`));
ok("20 state a specification", EVAL_SET.filter((q) => q.spec).length === 20, EVAL_SET.filter((q) => q.spec).length);
const amb = EVAL_SET.filter((q) => q.ambiguous);
ok("6 ambiguous single words", amb.length === 6 && amb.every((q) => !/\s/.test(q.text) && !q.spec), amb.map((q) => q.text));
ok("a specification names a number or a grade", EVAL_SET.filter((q) => q.spec).every((q) => /\d/.test(q.text)));
ok("texts are unique and short enough for the short-request route", new Set(EVAL_SET.map((q) => q.text.toLowerCase())).size === 40 && EVAL_SET.every((q) => q.text.length <= 80));
for (const p of ["grains", "sugar", "edible oils", "fertilizers", "cement", "steel rebar", "steel coil", "copper cable", "jet fuel", "LPG", "bitumen", "diesel generators", "solar panels",
  "power transformers", "distribution transformers", "battery storage", "PE pipes", "ductile iron pipe", "water meters", "reverse osmosis membranes", "reverse osmosis systems", "UPS",
  "server racks", "cooling", "medical devices", "surgical gloves", "excavators", "fire trucks"]) ok(`covers ${p}`, EVAL_SET.some((q) => q.product === p));
ok("the older benchmark list is untouched (the verification agent reads it)", QUERIES.length === 44 && QUERIES[0] === "white maize");

// the labeller's rows carry no verdict
const head = ["quality", "supplier", "country", "tier", "type", "products", "commodities", "website", "supplied", "industries", "hs_names", "hs_codes", "directory_contact", "kind",
  "match", "match_why", "match_evidence", "match_conflicts", "match_gaps", "match_version"];
const mk = (o: Record<string, string>) => head.map((k) => o[k] || "");
const grid = [head,
  mk({ supplier: "Acme Gensets Ltd", country: "TUR", tier: "1", type: "goods supplier", products: "diesel generators 20-2000 kVA", website: "acme.example", directory_contact: "A. Person; +90 000", kind: "maker",
    match: "supported", match_why: "Fits because its company's own product description names the product", match_evidence: "company's own product description", match_version: "match-x" }),
  mk({ supplier: "Blue Freight SA", country: "PAN", tier: "2", type: "works/services", supplied: "transport of diesel generators", match: "plausible", match_why: "Possible: evidence is contract items", match_evidence: "contract items", match_gaps: "named in a public contract it won" }),
  ...Array.from({ length: 30 }, (_, i) => mk({ supplier: `Filler ${i}`, country: "ZAF", match: "plausible" }))];
const sp = splitResults({ id: "Q17", text: "diesel generator 500 kVA 50 Hz" }, grid, (n) => (n === "Acme Gensets Ltd" ? { wt: "Acme - generator sets" } : undefined));
ok("top 25 only, in the order returned", sp.rows.length === 25 && sp.verdicts.length === 25 && sp.rows[0].supplier === "Acme Gensets Ltd" && sp.rows[1].rank === 2 && sp.rows[24].rank === 25);
ok("a blind row has exactly the labeller's fields", sp.rows.every((r) => JSON.stringify(Object.keys(r).sort()) === JSON.stringify([...BLIND_KEYS].sort())), Object.keys(sp.rows[0]));
const blindText = sp.rows.map((r) => JSON.stringify(r)).join("\n");
ok("no bucket, reason or evidence basis in the blind rows", !/supported|plausible|related|incompatible|Fits because|Possible:|contract items"|match-x/.test(blindText), blindText.slice(0, 300));
ok("the verdict is keyed by set, request id and rank", sp.verdicts[0].set === "product" && sp.verdicts[0].query_id === "Q17" && sp.verdicts[0].rank === 1 && sp.verdicts[0].bucket === "supported" && /Fits because/.test(sp.verdicts[0].reason) && sp.verdicts[1].gaps !== "");
ok("the evidence is what the matcher read, with the site title from the index record", /products: diesel generators 20-2000 kVA/.test(sp.rows[0].evidence) && /site title: Acme - generator sets/.test(sp.rows[0].evidence) && /supplied under contracts: transport of diesel/.test(sp.rows[1].evidence));
ok("website and contact flag", sp.rows[0].website === "acme.example" && sp.rows[0].has_contact === true && sp.rows[1].has_contact === false);
ok("evidence is capped at 400 characters and keeps the later parts", evidenceText({ p: "x".repeat(900), sp: "y".repeat(900), hd: "z".repeat(900) }).length <= EVIDENCE_MAX && /supplied under contracts: y/.test(evidenceText({ p: "x".repeat(900), sp: "y".repeat(900) })));
ok("an empty grid gives no rows", splitResults({ id: "Q01", text: "x" }, []).rows.length === 0 && splitResults({ id: "Q01", text: "x" }, [head]).rows.length === 0);
const sm = summarize([{ id: "Q17", returned: 25, total: 90, ms: 1 }, { id: "Q18", returned: 3, total: 3, ms: 1 }, { id: "Q19", returned: 0, total: 0, ms: 1 }], sp.verdicts);
ok("summary counts", sm.queries_run === 3 && sm.rows_returned === 25 && sm.rows_per_bucket.supported === 1 && sm.rows_per_bucket.plausible === 24 && sm.queries_under_5_rows === 2 && sm.queries_with_no_rows === 1);
ok("the summary holds no supplier", !/Acme|Filler|Blue Freight/.test(JSON.stringify(sm)));

// the tender sample
const T = (id: string, title_en: string, sector: string, notice_type = "tender") => ({ id, title_en, sector, notice_type, commodity: "", country: "KEN", region: "Africa" });
ok("goods purchase", stratumOf(T("1", "Supply of 500 kVA diesel generators", "Power & electrical equipment"), SERVICE_SECTOR) === "goods");
ok("development programme is not a goods purchase", stratumOf(T("2", "Agriculture value chains development for smallholders", "Agriculture & food", "Project Active"), SERVICE_SECTOR) === "non_goods");
ok("consulting is not a goods purchase", stratumOf(T("3", "Consultancy services for the feasibility study of a dam", "Consulting, business & financial services"), SERVICE_SECTOR) === "non_goods");
ok("works are not a goods purchase", stratumOf(T("4", "Construction of a primary school in the northern district", "Building construction works"), SERVICE_SECTOR) === "non_goods");
ok("framework agreement is mixed", stratumOf(T("5", "Framework agreement for the delivery of office supplies", "Other"), SERVICE_SECTOR) === "mixed");
ok("supply and installation is mixed", stratumOf(T("6", "Supply and installation of solar street lights", "Power & electrical equipment"), SERVICE_SECTOR) === "mixed");
ok("an unclear title is not sampled", stratumOf(T("7", "Notice 2026/114 for the regional office", "Other"), SERVICE_SECTOR) === "");
const many = [...Array.from({ length: 40 }, (_, i) => T(`g${i}`, `Supply of medical gloves batch ${i}`, i % 2 ? "Healthcare & pharmaceuticals" : "Agriculture & food")),
  ...Array.from({ length: 40 }, (_, i) => T(`n${i}`, `Consultancy services for audit number ${i}`, "Consulting, business & financial services")),
  ...Array.from({ length: 40 }, (_, i) => T(`m${i}`, `Framework agreement for the delivery of items ${i}`, "Other"))];
many.push(...Array.from({ length: 9 }, (_, i) => T(`p${i}`, `Rural livelihoods and resilience programme phase ${i}`, "Agriculture & food", "Project Active")));
ok("works at various places are not mixed", stratumOf(T("8", "Repair of tiles and drainage at various places in ward 15", "Repair, maintenance & installation"), SERVICE_SECTOR) === "non_goods");
ok("supply of maintenance is not a clear goods purchase", stratumOf(T("8b", "Provisioning for the supply of maintenance of medical equipment", "Healthcare & pharmaceuticals"), SERVICE_SECTOR) === "");
const pk = pickTenders(many, SERVICE_SECTOR);
ok("4 of the non-goods titles are development programmes", pk.filter((x) => x.stratum === "non_goods" && x.t.notice_type === "Project Active").length === 4);
ok("10 per stratum, 30 in all, no tender twice", pk.length === 30 && ["goods", "non_goods", "mixed"].every((s) => pk.filter((x) => x.stratum === s).length === 10) && new Set(pk.map((x) => x.t.id)).size === 30);
ok("the sample is stable for the same data", JSON.stringify(pickTenders([...many].reverse(), SERVICE_SECTOR).map((x) => x.t.id)) === JSON.stringify(pk.map((x) => x.t.id)));
const rq = tenderRequest({ ...T("9", "Supply of urea", "Agriculture & food"), commodity: "Fertilizers" });
ok("the tender request is the tender screen's (sector, title + commodity, country, region)", rq.text === "Supply of urea Fertilizers" && rq.sector === "Agriculture & food" && rq.country === "KEN" && rq.region === "Africa" && rq.n === 25);

// what the search derives from a tender title (lib/panel.ts): logged by the run
const w = queryWords("Agriculture value chains development for smallholder farmers in the northern region");
ok("title words: stop-words dropped, every other word of 3+ letters kept", JSON.stringify(w) === JSON.stringify(["agriculture", "value", "chains", "development", "smallholder", "farmers", "northern", "region"]), w);
ok("descriptors are dropped from the concepts unless nothing else is left", JSON.stringify(plainConceptWords(["granular", "urea"])) === '["urea"]' && JSON.stringify(plainConceptWords(["bulk"])) === '["bulk"]');
process.exit(fail ? 1 : 0);
