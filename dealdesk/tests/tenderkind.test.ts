// What a tender buys (lib/tenderkind.ts): goods, no goods, mixed or unknown, and the product phrases of a goods title.
// Every title below was written for this test (fictional buyers and places); none comes from the evaluation data.
// Run: npm test
import { tenderKind, type TenderKind } from "@/lib/tenderkind";
import { NO_GOODS_NOTE, queryWords, tenderPlan } from "@/lib/panel";
let fail = 0;
const ok = (name: string, cond: boolean, got?: unknown) => { if (!cond) fail++; console.log(`${cond ? "ok  " : "FAIL"} ${name}${cond ? "" : " - got " + JSON.stringify(got)}`); };
const K = (title: string, want: TenderKind["kind"], conf?: TenderKind["confidence"], extra: Record<string, string> = {}) => {
  const r = tenderKind({ title, ...extra });
  ok(`[${want}${conf ? " " + conf : ""}] ${title}${Object.keys(extra).length ? " " + JSON.stringify(extra) : ""}`, r.kind === want && (!conf || r.confidence === conf), r);
};
const P = (title: string, want: string[]) => {
  const r = tenderKind({ title });
  ok(`phrases of "${title}" = ${JSON.stringify(want)}`, (r.kind === "goods" || r.kind === "mixed") && JSON.stringify(r.goods_phrases) === JSON.stringify(want), r);
};

// ---- goods: English ----
K("Supply and delivery of 500 kVA diesel generators to Northfield hospital, Lot 2", "goods", "high");
K("Supply of medical gloves and surgical masks", "goods", "high");
K("Procurement of laboratory reagents for the national reference laboratory", "goods", "high");
K("Purchase of 40 desktop computers", "goods", "high");
K("Invitation to bid for the supply of granular urea 46% in 50 kg bags", "goods", "high");
K("Supply of spare parts for the maintenance of fire trucks", "goods", "high");
K("Supply of cleaning materials and detergents", "goods", "high");
K("Supply of construction materials for the Eastbrook school project", "goods", "high");
K("Supply of training manuals to district education offices", "goods", "high");
K("Acquisition of two ambulances", "goods", "high");
K("Provision of office furniture for the new regional office", "goods", "high");
K("RFQ-2031-044: Supply and delivery of HDPE pipes DN 110", "goods", "high");
K("Ministry of Public Works - supply of bitumen 60/70", "goods", "high");
// ---- goods: French, Spanish, Portuguese ----
K("Fourniture de matériel informatique au profit de la direction régionale", "goods", "high");
K("Acquisition de médicaments essentiels pour les centres de santé", "goods", "high");
K("Fourniture et livraison de 200 tonnes de riz", "goods", "high");
K("Fourniture de produits d'entretien", "goods", "high");
K("Fourniture de matériaux de construction", "goods", "high");
K("Adquisición de equipos médicos para el hospital regional", "goods", "high");
K("Suministro de material de limpieza", "goods", "high");
K("Compra de fertilizantes para pequeños productores", "goods", "high");
K("Servicio de suministro de combustible diésel", "goods", "high");
K("Aquisição de computadores portáteis para as escolas", "goods", "high");
K("Fornecimento de medicamentos e material de consumo", "goods", "high");
K("Aquisição de géneros alimentícios", "goods", "high");

// ---- no goods: works ----
K("Rehabilitation of water supply system", "non_goods", "high");
K("Construction of a three-classroom block at Hillview primary school", "non_goods", "high");
K("Road works on the Lakeside bypass", "non_goods", "high");
K("Procurement of works for the construction of a health post", "non_goods", "high");
K("Rural roads rehabilitation project", "non_goods", "high");
K("Repair of tiles and drainage at various places in ward 15", "non_goods", "high");
K("Travaux de construction d'un forage équipé", "non_goods", "high");
K("Réhabilitation de la piste rurale de Kanda", "non_goods", "high");
K("Obras de pavimentación de la calle principal", "non_goods", "high");
K("Mejoramiento del sistema de agua potable", "non_goods", "high");
K("Empreitada de reabilitação da escola básica", "non_goods", "high");
K("Construção de um centro de saúde", "non_goods", "high");
// ---- no goods: services, consulting, studies ----
K("Supply of consultancy services", "non_goods", "high");
K("Procurement of insurance services", "non_goods", "high");
K("Technical assistance for procurement reform", "non_goods", "high");
K("Provision of security guards", "non_goods", "high");
K("Consultancy services for the supervision of the supply and installation of solar pumps", "non_goods", "high");
K("Feasibility study for a regional grain storage facility", "non_goods", "high");
K("Audit of the financial statements of the rural electrification fund", "non_goods", "high");
K("Maintenance of diesel generators", "non_goods", "high");
K("Provision of cleaning services for the head office", "non_goods", "high");
K("Provisioning for the supply of maintenance of medical equipment", "non_goods", "high");
K("Training of community health workers", "non_goods", "high");
K("Hire of vehicles for the census", "non_goods", "high");
K("Software development for a land registry system", "non_goods", "high");
K("Supply of labour for harvesting", "non_goods", "high");
K("Recrutement d'un consultant pour l'étude de faisabilité", "non_goods", "high");
K("Prestation de services de gardiennage des locaux", "non_goods", "high");
K("Assistance technique pour la réforme des finances publiques", "non_goods", "high");
K("Servicio de vigilancia y seguridad privada", "non_goods", "high");
K("Consultoría para la elaboración del plan maestro", "non_goods", "high");
K("Contratación de servicios de limpieza", "non_goods", "high");
K("Mantenimiento de vehículos", "non_goods", "high");
K("Prestação de serviços de manutenção predial", "non_goods", "high");
K("Contratação de empresa para serviços de vigilância", "non_goods", "high");
K("Elaboração de estudo de viabilidade", "non_goods", "high");
// ---- no goods: programmes ----
K("Agriculture value chains development for smallholder farmers in the northern region", "non_goods", "high");
K("Rural livelihoods and resilience programme phase 2", "non_goods", "high");
K("Public financial management reform", "non_goods", "high");

// ---- mixed ----
K("Supply and installation of solar street lights", "mixed", "high");
K("Supply, installation and commissioning of a 1 MVA transformer", "mixed", "high");
K("Design, supply and build of a 2 MW solar plant", "mixed", "high");
K("Supply of medical equipment and training of staff", "mixed", "high");
K("Works contract for supply and laying of pipes", "mixed");
K("Construction of a clinic and supply of medical equipment", "mixed");
K("Framework agreement for the supply of stationery", "mixed");
K("Supply of laboratory equipment in 4 lots", "mixed");
K("Supply of generators including installation", "mixed");
K("Maintenance services including supply of spare parts", "mixed");
K("Turnkey supply of a water treatment plant", "mixed", "high");
K("Installation of CCTV cameras", "mixed", "low");
K("Fourniture et pose de compteurs d'eau", "mixed", "high");
K("Suministro e instalación de luminarias LED", "mixed", "high");
K("Fornecimento e instalação de painéis solares", "mixed", "high");
K("Adquisición de equipos y capacitación del personal", "mixed", "high");

// ---- unknown or low confidence: goods are never guessed ----
K("Expression of interest", "unknown", "low");
K("Annual procurement plan", "unknown", "low");
K("Provision of meals", "unknown", "low");
K("Laboratory equipment for district hospitals", "goods", "low");
K("Water sector support", "unknown", "low", { sector: "" });
K("Northern corridor", "non_goods", "low", { sector: "Engineering & architecture services" });
ok("an empty title is unknown", tenderKind({ title: "" }).kind === "unknown" && tenderKind({ title: "" }).goods_phrases.length === 0);
ok("a goods noun alone never gives high confidence", tenderKind({ title: "Medical equipment" }).confidence === "low");
ok("an undecided title is read from the description, with low confidence", (() => { const r = tenderKind({ title: "Tender 14", description: "Supply of maize seed to farmer groups" }); return r.kind === "goods" && r.confidence === "low"; })());

// ---- structured hints come first ----
K("Laboratory reagents", "goods", "high", { category: "Goods" });
K("Diesel generators 500 kVA", "goods", "high", { cpv: "31121000-1" });
K("Accounting package", "goods", "high", { cpv: "48443000" });
K("District hospital", "non_goods", "high", { cpv: "45215140-8" });
K("District hospital", "non_goods", "high", { category: "Works" });
K("Northern grid", "non_goods", "high", { category: "consultingServices" });
K("Northern grid", "non_goods", "high", { cpv: "71311000" });
K("Supply and installation of lifts", "mixed", "high", { category: "goods" });
K("Supply of cement", "mixed", "low", { category: "works" });
K("Fournitures de bureau", "goods", "high", { category: "FOURNITURES" });
K("Reprise des peintures", "non_goods", "high", { category: "travaux" });
K("Pumps", "unknown", "low", { cpv: "51100000" });
ok("the category is read before the CPV code", tenderKind({ title: "Pumps", category: "goods", cpv: "45000000" }).kind === "goods");
ok("the reason names the hint", /procurement category/.test(tenderKind({ title: "Pumps", category: "goods" }).why) && /CPV division 45/.test(tenderKind({ title: "Site", cpv: "45000000" }).why));

// ---- product phrases: procurement wording, places, buyers, lots, references and dates removed; quantities kept ----
P("Supply and delivery of 500 kVA diesel generators to Northfield hospital, Lot 2", ["500 kVA diesel generators"]);
P("Supply of medical gloves and surgical masks", ["medical gloves", "surgical masks"]);
P("Procurement of laboratory reagents for the national reference laboratory", ["laboratory reagents"]);
P("Purchase of 40 desktop computers", ["40 desktop computers"]);
P("Invitation to bid for the supply of granular urea 46% in 50 kg bags", ["granular urea 46%"]);
P("RFQ-2031-044: Supply and delivery of HDPE pipes DN 110", ["HDPE pipes DN 110"]);
P("Supply of office desks, chairs and filing cabinets (Ref. ICB/2031/007)", ["office desks", "chairs", "filing cabinets"]);
P("Supply of 10,000 MT of white maize, Riverton County", ["10,000 MT of white maize"]);
P("Supply of the following items: Lot 1 - 2031", []);
P("Supply and installation of solar street lights at Greenfield market", ["solar street lights"]);
P("Supply of medical equipment and training of staff", ["medical equipment"]);
P("Works contract for supply and laying of pipes", ["pipes"]);
P("Construction of a clinic and supply of medical equipment", ["medical equipment"]);
P("Fourniture et livraison de 200 tonnes de riz", ["200 tonnes de riz"]);
P("Acquisition de médicaments essentiels pour les centres de santé", ["médicaments essentiels"]);
P("Adquisición de equipos médicos para el hospital regional", ["equipos médicos"]);
P("Aquisição de computadores portáteis para as escolas", ["computadores portáteis"]);
P("Supply of 5 to 10 tonne tipper trucks", ["5 to 10 tonne tipper trucks"]);
P("Supply of bitumen 60/70 - Lot 3", ["bitumen 60/70"]);
ok("no phrases for a title that buys no goods", tenderKind({ title: "Supply of consultancy services" }).goods_phrases.length === 0 && tenderKind({ title: "Road works" }).goods_phrases.length === 0);
ok("at most three phrases", tenderKind({ title: "Supply of pens, pencils, erasers, rulers and staplers" }).goods_phrases.length === 3);
ok("the same title always gives the same answer", JSON.stringify(tenderKind({ title: "Supply of cement" })) === JSON.stringify(tenderKind({ title: "Supply of cement" })));

// ---- the flag (lib/panel.ts tenderPlan): off by default, and off means the search is not touched ----
const nonGoods = { text: "Rehabilitation of water supply system Water", sector: "Water", tender: { title: "Rehabilitation of water supply system" } };
const goods = { text: "Supply and delivery of 500 kVA diesel generators to Northfield hospital, Lot 2 Generators", tender: { title: "Supply and delivery of 500 kVA diesel generators to Northfield hospital, Lot 2" } };
for (const flag of [undefined, "", "off", "ON", "1", "true"]) ok(`flag ${JSON.stringify(flag)}: no plan, whatever the tender`, tenderPlan(nonGoods, flag) === null && tenderPlan(goods, flag) === null);
ok("flag on, but the request is not a tender request: no plan", tenderPlan({ text: "Rehabilitation of water supply system" }, "on") === null && tenderPlan({ text: "x", tender: { title: " " } }, "on") === null);
const pn = tenderPlan(nonGoods, "on"), pg = tenderPlan(goods, "on");
ok("flag on, no goods with high confidence: blocked, with the note", !!pn && pn.block && pn.text === null && pn.kind.kind === "non_goods" && /nothing to source/.test(NO_GOODS_NOTE), pn);
ok("flag on, goods: searched by the product phrase, not by the title words", !!pg && !pg.block && pg.text === "500 kVA diesel generators", pg);
ok("the phrase leaves the place and the lot out of the search words", JSON.stringify(queryWords(pg!.text!)) === JSON.stringify(["500", "kva", "diesel", "generators"]) && queryWords(goods.text).includes("northfield"));
ok("flag on, mixed: searched by the goods part", tenderPlan({ text: "t", tender: { title: "Supply of medical equipment and training of staff" } }, "on")?.text === "medical equipment");
ok("flag on, low confidence or unknown: today's behaviour", [{ title: "Northern corridor" }, { title: "Annual procurement plan" }, { title: "Provision of meals" }].every((t) => { const p = tenderPlan({ text: t.title, sector: "Engineering & architecture services", tender: t }, "on"); return !!p && !p.block && p.text === null; }));
ok("flag on, goods but no phrase: today's behaviour", (() => { const p = tenderPlan({ text: "t", tender: { title: "Supply of the following items: Lot 1 - 2031" } }, "on"); return !!p && !p.block && p.text === null; })());
ok("flag on: the tender's category is used", tenderPlan({ text: "t", tender: { title: "District hospital", category: "works" } }, "on")?.block === true);
process.exit(fail ? 1 : 0);
