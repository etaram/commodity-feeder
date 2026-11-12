// Material gathering for a case (lib/casematerial.ts): found and not found, and that every fact carries its source
// and its date. The index and the contact lookup are in-memory stand-ins; no model, no network. All names are made up.
import { gatherMaterial, INDEX_SOURCE, MAX_ITEMS, MAX_MATERIAL_BYTES, materialText, UNIVERSE_SOURCE, type MaterialDeps } from "@/lib/casematerial";
import type { Supplier } from "@/lib/index";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const NOW = Date.parse("2026-11-12T10:00:00Z");

const MILL: Supplier = { n: "Example Paper Mills Ltd", c: "IND", rg: "South Asia", tr: "1", s: "Chemicals & plastics", s2: "Textiles, apparel & leather", ty: "goods supplier; manufacturer", p: "kraft paper; sack paper; paper bags",
  web: "https://mills.example", wb: "company register", hs: "4804 4819", hd: "Kraft paper, uncoated; Paper sacks and bags", sh: 42, w: 3, u: 1250000, bc: "KEN TZA", lw: "2026-08-03", why: "exporter with awards", sp: "paper sacks", cm: "paper", in: "pulp and paper",
  ct: "Mr A. Person; +91 00 0000; export@mills.example", rc: 1 };
const ROWS: Supplier[] = [MILL, { n: "Example Trading Co", c: "ARE", td: "yes", p: "general goods" }, { n: "Northern Example Steel GmbH", c: "DEU", p: "steel pipes" }, { n: "Northern Example Steel SA", c: "ESP", p: "rebar" },
  { n: "Twin Example Ltd", c: "KEN", p: "maize" }, { n: "Twin Example Ltd", c: "UGA", p: "beans" }, { n: "Bare Example", c: "PER" }];
let contactCalls: string[] = [], indexReads = 0;
const deps = (over: Partial<MaterialDeps> = {}): MaterialDeps => ({ now: () => NOW, suppliers: async () => { indexReads++; return { rows: ROWS }; },
  contact: async (n, c) => { contactCalls.push(`${n}|${c}`); return n === MILL.n ? { email: "sales@mills.example", phone: "+91 11 5550 0000", website: "https://mills.example", website_source: "official site", address: "", legal_id: "" } : null; }, ...over });
const complete = (items: { fact: string; source: string; date: string }[]) => items.length > 0 && items.every((i) => i.fact.trim() && i.source.trim() && /^\d{4}-\d{2}-\d{2}$/.test(i.date));

(async () => {
  const m = await gatherMaterial(deps(), { company: "Example Paper Mills", country: "IND" });
  ok(m.found && m.company === "Example Paper Mills Ltd" && m.country === "IND", "found by its name without the legal suffix; the case takes the name and country of the record");
  ok(complete(m.items), "every fact has a source and a date");
  ok(m.items.every((i) => i.source.startsWith(INDEX_SOURCE) || i.source.startsWith(UNIVERSE_SOURCE)) && m.items.every((i) => /field|column|rule/.test(i.source)), "every source names the dataset and the field, column or rule it was read from");
  const text = materialText(m.items);
  for (const [what, rx] of [["products", /Products on record: kraft paper/], ["sector", /Main sector on record: Chemicals & plastics; other sectors: Textiles/], ["type", /Type on record: goods supplier; manufacturer/], ["maker by rule", /Reads as a manufacturer by the system's naming rule.*not a verified fact/],
    ["tier", /Tier 1 in the system's ranking; reason on record: exporter with awards/], ["website", /Website on record: https:\/\/mills\.example \(basis: company register\)/], ["customs lines", /Customs headings on record: Kraft paper, uncoated; Paper sacks and bags \(HS 4804 4819\)/],
    ["shipments", /Export shipments in the last 12 months on record: 42/], ["awards", /Public contract awards on record: 3, estimated USD 1,250,000; buyer countries: KEN TZA; last award 2026-08-03/], ["open conflict", /open conflict flag/]] as [string, RegExp][])
    ok(rx.test(text), `the material holds the record's ${what}`);
  ok(m.items.find((i) => /Public contract awards/.test(i.fact))?.date === "2026-08-03" && m.items.find((i) => /Products on record/.test(i.fact))?.date === "2026-11-12", "a fact with its own date keeps it; the others carry the day the record was read");
  ok(m.record_updated === "" && /no per-record update date/.test(m.note), "no 'last updated' date is claimed: the index has none, and the note says so");
  ok(m.contact_email === "sales@mills.example" && /Published business contact on record: e-mail sales@mills\.example; phone \+91 11 5550 0000/.test(text) && contactCalls.join() === "Example Paper Mills Ltd|IND", "the stored business contact is looked up by the record's exact name and country");
  ok(/directory: export@mills\.example/.test(text) && !/A\. Person/.test(text) && !/\+91 00 0000/.test(text), "of a directory contact only the e-mail address is passed on, never the person");
  ok(text.split("\n").every((l, i) => l.startsWith(`${i + 1}. `) && /\[source: .+; date: \d{4}-\d{2}-\d{2}\]$/.test(l)), "the text for the research role is one numbered line per fact, each ending with its source and date");

  // ---- not found
  contactCalls = [];
  const no = await gatherMaterial(deps(), { company: "Nowhere Industries" });
  ok(!no.found && no.items.length === 0 && /not in the supplier index/.test(no.note) && contactCalls.length === 0, "a company that is not in the index: found is false, no facts, no contact lookup");
  ok(!(await gatherMaterial(deps(), { company: "Example Paper Mills", country: "CHN" })).found, "the right name in another country is not found");
  const amb = await gatherMaterial(deps(), { company: "Northern Example Steel" });
  ok(!amb.found && amb.candidates.length === 2 && amb.candidates.includes("Northern Example Steel GmbH (DEU)") && /fits 2 companies/.test(amb.note), "a name that fits two companies is not guessed: found is false and the candidates are listed");
  const twin = await gatherMaterial(deps(), { company: "Twin Example Ltd" });
  ok(!twin.found && twin.candidates.length === 2 && (await gatherMaterial(deps(), { company: "Twin Example Ltd", country: "uga" })).found, "the same name in two countries needs the ISO3 code, and is found with it");
  ok(!(await gatherMaterial(deps(), { company: "  " })).found && !(await gatherMaterial(deps(), { company: "Ltd" })).found, "an empty name, or one that is only a legal suffix, is not found");
  const down = await gatherMaterial(deps({ suppliers: async () => ({ rows: [], error: "WEB_INDEX_KEY is not configured" }) }), { company: "Example Paper Mills" });
  const thrown = await gatherMaterial(deps({ suppliers: async () => { throw new Error("HTTP 500"); } }), { company: "Example Paper Mills" });
  ok(!down.found && /could not be read: WEB_INDEX_KEY/.test(down.note) && !thrown.found && /HTTP 500/.test(thrown.note), "an index that cannot be read is not found, and the note says why");

  // ---- edges
  const loose = await gatherMaterial(deps(), { company: "Paper Mills Example" });
  ok(loose.found && /matched by every word of the name asked for/.test(loose.items[0].fact) && complete(loose.items), "one record that holds every word of the name is used, and the first fact says the match was not exact");
  const trader = await gatherMaterial(deps(), { company: "Example Trading Co" });
  ok(trader.found && /flagged as a trader/.test(materialText(trader.items)) && /Reads as a trader/.test(materialText(trader.items)) && trader.contact_email === "" && /No business contact is stored/.test(trader.note), "a trader is described as one; with no stored contact the note says so and no address is made up");
  const bare = await gatherMaterial(deps(), { company: "Bare Example" });
  ok(bare.found && complete(bare.items) && /does not say whether this is a manufacturer or a trader/.test(materialText(bare.items)) && !/Products on record/.test(materialText(bare.items)), "a record with only a name yields only what it holds, and says the type is unknown");
  const failing = await gatherMaterial(deps({ contact: async () => { throw new Error("lookup 500"); } }), { company: "Example Paper Mills" });
  ok(failing.found && /stored contact could not be read/.test(failing.note) && failing.contact_email === "export@mills.example", "a contact lookup that fails does not lose the record; the note says the contact could not be read");
  const fat: Supplier = { ...MILL, n: "Fat Example Ltd", c: "BRA", p: "p ".repeat(400), sp: "s ".repeat(400), hd: "h ".repeat(400), in: "i ".repeat(300), why: "w ".repeat(300) };
  const many = await gatherMaterial(deps({ suppliers: async () => ({ rows: [fat, { ...fat }, { ...fat }, { ...fat }] }) }), { company: "Fat Example Ltd" });
  ok(many.found && many.items.length <= MAX_ITEMS && Buffer.byteLength(materialText(many.items), "utf8") <= MAX_MATERIAL_BYTES && many.items.every((i) => i.fact.length <= 400) && complete(many.items) && /holds 4 records/.test(many.items[0].fact),
    "several long records stay inside the research role's input bound; facts are left out whole, never cut mid-way");
  if (fail) { console.log(`${fail} failed`); process.exit(1); }
})();
