import type { Supplier } from "@/lib/index";

// What a supplier is to Sinder, fixed at load time (mirrors leads/universe.py so an index built before the rule
// gets the same treatment; a row the builder already corrected carries qv >= 2 and is left alone).
// - Identity beats the contract mix: a company whose name or own site says defence, laundry or cleaning is that.
// - Sinder buys goods across borders. A company that only delivers services on site (laundry, cleaning, catering,
//   maintenance, consulting, engineering design, training) is not a supplier for it, however much it won, so its
//   quality is scaled down and it ranks after the goods suppliers of its tier.
export const DEFENCE_ID = /\b(defen[cs]e|military|armament|arms|ammunition|munitions|missiles?|ordnance|leonardo|rafael|elbit|thales|rheinmetall|saab|bae systems|kongsberg|nexter|knds|krauss-?maffei|hensoldt|aselsan|roketsan|mbda|lockheed|raytheon|northrop|general dynamics|iveco defence|patria|nammo|fn herstal|colt|beretta|glock|sig sauer)\b/i;
export const CLEANING_ID = /\b(laundry|laundries|linen|textile (rental|service)|workwear rental|vask\w*|w[äa]scherei|blanchisserie|lavander[ií]a|wasserij|tv[äa]tteri|pesula|pralnia|cleaning|rengøring|reinigung|nettoyage|limpieza|schoonmaak|st[äa]d\w*|facility services|facility management|catering|canteen)\b/i;
export const SERVICE_SECTOR = new Set(["Repair, maintenance & installation", "Transport & logistics services", "Engineering & architecture services",
  "Consulting, business & financial services", "Environment, waste & cleaning", "Education, social & hospitality services"]);
const GOODS_HINT = /\b(manufactur\w*|producers?|factory|mill|supplier of|supplies of|equipment|machinery|vehicles|parts|spare|products?)\b/i;

export function isServiceOnly(s: Supplier): boolean {
  const ty = String(s.ty || "");
  if (/goods supplier|manufactur|producer/i.test(ty) || s.td === "yes") return false;
  if (s.hs || s.sh) return false; // customs exports are goods
  if (CLEANING_ID.test(`${s.n || ""} ${s.wt || ""} ${s.in || ""}`)) return true;
  return SERVICE_SECTOR.has(String(s.s || "")) && (/services/i.test(ty) || !GOODS_HINT.test(`${s.p || ""} ${s.sp || ""}`));
}

export function normalizeSuppliers(rows: Supplier[]) {
  for (const s of rows as (Supplier & { qv?: number; _n?: 1 })[]) {
    if (s._n || (s.qv || 0) >= 2) continue;
    s._n = 1;
    const idText = `${s.n || ""} ${s.in || ""}`, siteText = `${s.n || ""} ${s.wt || ""} ${s.in || ""}`;
    const setMain = (sec: string) => { if (s.s === sec) return; const rest = [s.s, ...String(s.s2 || "").split(/;\s*/)].filter((x) => x && x !== sec); s.s = sec; s.s2 = rest.slice(0, 2).join("; "); };
    if (DEFENCE_ID.test(idText)) setMain("Defence & security");
    else if (CLEANING_ID.test(siteText)) setMain("Environment, waste & cleaning");
    else if (SERVICE_SECTOR.has(String(s.s || "")) || !s.s) {
      // goods the company says it makes outrank the mix of what public buyers bought from it
      const own = sectorOf(`${s.n || ""} ${s.wt || ""} ${s.p || ""} ${s.in || ""} ${s.hd || ""}`);
      if (own) setMain(own);
    }
    if (isServiceOnly(s)) { s.q = Math.round((Number(s.q) || 0) * 0.6); if (!/services/i.test(String(s.ty || ""))) s.ty = "works/services"; }
  }
  return rows;
}

// Sector of a company found on the web (research results saved to the Web Suppliers tab), from what it says it
// makes; mirrors the goods part of leads/sectors.py, first match wins, goods before services.
const SECTOR_OF: [string, RegExp][] = [
  ["Defence & security", DEFENCE_ID],
  ["Agriculture & food", /\b(food|fish|seafood|tuna|sardine|shrimp|meat|poultry|dairy|milk powder|coffee|cocoa|tea|fruit|vegetables?|nuts?|cashew|spices?|grain|wheat|maize|corn|rice|sugar|edible oil|palm oil|sunflower oil|soybeans?|flour|fertili[sz]ers?|urea|seeds?|animal feed|canned|cannery)\b/i],
  ["Energy, fuels & utilities", /\b(diesel|gasoil|fuel|jet a-?1|lpg|lng|crude|petroleum|bitumen|coal|natural gas|refiner\w*)\b/i],
  ["Power & electrical equipment", /\b(transformers?|switchgear|cables?|conductors?|solar|photovoltaic|pv modules?|inverters?|generators?|gensets?|batter(y|ies)|meters?|electrical)\b/i],
  ["Mining, minerals & metals", /\b(steel|rebar|billets?|iron ore|copper|alumin(i)?um|zinc|nickel|metals?|alloys?|scrap|mining|smelt\w*|foundr\w*)\b/i],
  ["Chemicals & plastics", /\b(chemicals?|reagents?|chlorine|caustic soda|sulphur|sulfur|plastics?|polyethylene|pvc|resins?|polymers?)\b/i],
  ["Construction materials & building systems", /\b(cement|clinker|aggregates?|bricks?|tiles?|ceramics?|glass|pipes?|timber|roofing|asphalt|ready-?mix|concrete)\b/i],
  ["Healthcare & pharmaceuticals", /\b(medical|hospital|pharma\w*|diagnostic\w*|syringes?|gloves|ppe|surgical|x-?ray|ultrasound|ventilators?)\b/i],
  ["Scientific & measuring instruments", /\b(laborator(y|ies)|scientific|measuring|instruments?|analy[sz]ers?|spectromet\w*|microscopes?|calibration)\b/i],
  ["ICT & telecom", /\b(servers?|computers?|laptops?|telecom\w*|fib(er|re) optic|routers?|switches|networking|software|data ?cent(er|re)s?|cctv)\b/i],
  ["Vehicles, rolling stock, ships & aircraft", /\b(vehicles?|trucks?|buses|cars|locomotives?|wagons?|ships?|vessels?|boats?|aircraft|helicopters?|tyres?|tires?)\b/i],
  ["Industrial & construction machinery", /\b(machinery|machines?|pumps?|compressors?|valves?|excavators?|loaders?|cranes?|tractors?|bearings?|motors?|spare parts|hydraulic\w*)\b/i],
  ["Textiles, apparel & leather", /\b(textiles?|fabrics?|garments?|apparel|clothing|uniforms?|footwear|boots|leather|tents?|blankets?)\b/i],
  ["Furniture, appliances & consumer goods", /\b(furniture|appliances?|stationery|office supplies|household)\b/i],
  ["Water & wastewater", /\b(water treatment|desalination|wastewater|water meters?|membranes?)\b/i],
];
export function sectorOf(text: string): string {
  for (const [sec, rx] of SECTOR_OF) if (rx.test(text || "")) return sec;
  return "";
}
