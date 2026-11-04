import Papa from "papaparse";

// Logistics: who moves, clears, inspects and insures the goods of a deal.
// Source: data/logistics/logistics_providers.csv, every row checked on the organisation's official site or the
// government body that runs it (README there). Matching for one deal:
// - the destination country's official import programmes (pre-shipment inspection, conformity certificates, cargo
//   tracking notes) come first and are marked required: a shipment without them is stopped at the port;
// - customs: the destination country's broker registry or association, and Israeli brokers when Israel is the
//   origin or the destination;
// - freight: forwarders, carriers, breakbulk and air cargo that operate in the origin and the destination regions;
//   project cargo first for heavy equipment, defence-capable ones first for defence goods;
// - inspection companies and cargo insurance by region.
const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/logistics/logistics_providers.csv";
export type Lg = Record<string, string>;
let mem: { at: number; rows: Lg[] } | null = null;

export async function logisticsRows(): Promise<Lg[]> {
  if (mem && Date.now() - mem.at < 3_600_000) return mem.rows;
  const r = await fetch(RAW, { cache: "no-store" }).catch(() => null);
  const rows = r && r.ok ? (Papa.parse<Lg>(await r.text(), { header: true, skipEmptyLines: true }).data || []) : [];
  mem = { at: Date.now(), rows };
  return rows;
}

const list = (v: string) => String(v || "").split(";").map((x) => x.trim()).filter(Boolean);
const PROGRAMME = /pvoc|soncap|saber|easypass|ecas|bis\b|besc|ectn|cargo tracking|conformity|factory registration|aci\b|verification of conformity/i;
const HEAVY = /transformer|turbine|generator|crane|heavy|substation|boiler|locomotive|project/i;

export type LgQuery = { sector?: string; region?: string; buyerCountry?: string; origins?: string[]; originRegions?: string[]; title?: string; defence?: boolean };
export async function logisticsFor(q: LgQuery) {
  const rows = await logisticsRows();
  const dest = (q.buyerCountry || "").toUpperCase(), origins = new Set((q.origins || []).map((x) => x.toUpperCase()));
  const regs = new Set([q.region || "", ...(q.originRegions || [])].filter(Boolean));
  const israel = dest === "ISR" || origins.has("ISR") || !origins.size;
  const heavy = HEAVY.test(q.title || "") || /Power|Industrial|Vehicles|Transport & civil/.test(q.sector || "");
  const out: { f: Lg; group: string; sc: number; why: string[]; required: boolean }[] = [];
  for (const f of rows) {
    const regions = list(f.regions), services = list(f.services).join(" ").toLowerCase(), why: string[] = [];
    const regOk = regions.includes("global") || [...regs].some((r) => regions.includes(r));
    let group = "", sc = 0, required = false;
    if (f.category === "inspection" && PROGRAMME.test(`${f.name} ${f.short_name} ${f.scale_note}`) ) {
      if (f.country_hq !== dest) continue;
      group = "required"; required = true; sc = 100; why.push(`required for imports into ${dest}`);
    } else if (f.category === "customs") {
      if (f.country_hq === dest) { group = "customs"; sc = 50; why.push(`customs brokers in ${dest}`); }
      else if (f.country_hq === "ISR" && israel) { group = "customs"; sc = 40; why.push("Israeli customs broker"); }
      else if (/compliance|dangerous|explosive|class 1/i.test(`${services} ${f.scale_note}`) && q.defence) { group = "customs"; sc = 35; why.push("trade compliance for controlled goods"); }
      else continue;
    } else if (["forwarder", "ocean_carrier", "breakbulk", "air_cargo"].includes(f.category)) {
      if (!regOk) continue;
      group = "freight"; sc = 10 + (regions.includes(q.region || "") ? 6 : 0);
      if (heavy && /heavy-lift|project cargo|breakbulk/.test(services)) { sc += 8; why.push("project cargo and heavy lift"); }
      if (q.defence && f.defence_ok === "yes") { sc += 8; why.push("handles defence cargo"); }
      if (q.defence && f.defence_ok === "no") continue;
      if (String(f.israel_presence).toLowerCase().startsWith("yes")) { sc += 4; why.push("office in Israel"); }
      if (regions.includes(q.region || "")) why.push(`active in ${q.region}`);
    } else if (f.category === "inspection") {
      if (!regOk) continue;
      group = "inspection"; sc = 8; why.push("pre-shipment and quality inspection");
    } else if (f.category === "insurance") {
      group = "insurance"; sc = 5 + (f.country_hq === "ISR" ? 3 : 0); why.push(f.country_hq === "ISR" ? "Israeli marine cargo insurer" : "marine cargo insurance");
    } else continue;
    out.push({ f, group, sc, why, required });
  }
  out.sort((a, b) => b.sc - a.sc);
  const take = (g: string, n: number) => out.filter((x) => x.group === g).slice(0, n);
  const pick = (x: { f: Lg; why: string[]; required: boolean; group: string }) => ({ ...x.f, why: x.why, required: x.required, group: x.group });
  return [...take("required", 4), ...take("customs", 4), ...take("freight", 6), ...take("inspection", 3), ...take("insurance", 3)].map(pick);
}

export async function logisticsList() {
  return (await logisticsRows()).map((f) => ({ ...f, programme: f.category === "inspection" && PROGRAMME.test(`${f.name} ${f.short_name} ${f.scale_note}`) }));
}
