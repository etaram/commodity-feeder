import { RAW_ROOT } from "@/lib/rawbase";
import Papa from "papaparse";
import NAMES from "@/lib/countrynames.json";

// How strong the basis for a route is (spec phase 5): "active in Europe" is not a route. Per suggestion:
//   required - the destination's own import programme (stops the shipment if missing)
//   lane     - the provider names the destination or the origin in its lanes, ports or services
//   region   - a directory entry that operates in the region only; a quote is the only proof of the lane
const NM = NAMES as Record<string, string[]>;
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const mentions = (text: string, iso: string) => !!iso && (new RegExp(`\\b${iso}\\b`).test(text) || (NM[iso] || []).some((n) => new RegExp(`\\b${esc(n)}\\b`, "i").test(text)));

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
const RAW = `${RAW_ROOT}/data/logistics/logistics_providers.csv`;
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
  const laneText = (f: Lg) => `${f.key_lanes || ""} ${f.ports || ""} ${f.services || ""} ${f.scale_note || ""}`;
  const pick = (x: { f: Lg; why: string[]; required: boolean; group: string }) => {
    const t = laneText(x.f), dst = mentions(t, dest), org = [...origins].find((o) => mentions(t, o));
    const basis = x.required ? "required" : (dst || org) ? "lane" : x.group === "customs" && x.f.country_hq === dest ? "lane" : "region";
    const basis_note = x.required ? `required by ${dest} import rules` : basis === "lane" ? `names ${[dst ? dest : "", org || ""].filter(Boolean).join(" and ") || dest} in its lanes or services` : "regional directory entry; no evidence for this exact lane";
    return { ...x.f, why: x.why, required: x.required, group: x.group, basis, basis_note };
  };
  const BR: Record<string, number> = { required: 0, lane: 1, region: 2 };
  // within each group, a provider with evidence for this lane comes before a regional directory entry
  const grp = (g: string, n: number) => out.filter((x) => x.group === g).map(pick).sort((a, b) => BR[a.basis] - BR[b.basis]).slice(0, n);
  return [...grp("required", 4), ...grp("customs", 4), ...grp("freight", 6), ...grp("inspection", 3), ...grp("insurance", 3)];
}

export async function logisticsList() {
  return (await logisticsRows()).map((f) => ({ ...f, programme: f.category === "inspection" && PROGRAMME.test(`${f.name} ${f.short_name} ${f.scale_note}`) }));
}
