import Papa from "papaparse";
import { allTenders } from "@/lib/panel";

// Two morning pages from the system's own data.
// General: what matters today worldwide (big new tenders open to foreign firms, what closes this week, the theses,
// the headlines). Focus: the same layers seen through one lens (commodities, defence, engineering, data centers,
// energy, medical equipment): a lens is a set of sectors plus product words; a notice belongs to it when either
// matches, and ranks by the brain's fit, lifted when both match.
const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/leads";
type Row = Record<string, string>;
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/[,$]/g, "")); return Number.isFinite(n) ? n : 0; };

export type Lens = { id: string; en: string; he: string; sectors: string[]; kw: RegExp; not?: RegExp };
export const LENSES: Lens[] = [
  { id: "commodities", en: "Commodities", he: "קומודיטיז",
    sectors: ["Agriculture & food", "Mining, minerals & metals", "Energy, fuels & utilities", "Chemicals & plastics", "Construction materials & building systems"],
    kw: /\b(wheat|maize|corn|rice|sugar|edible oil|palm oil|sunflower oil|soybean|fertili[sz]er|urea|dap|npk|diesel|gasoil|fuel|jet a-?1|lpg|coal|bitumen|asphalt|cement|clinker|steel|rebar|billet|copper|aluminium|aluminum|zinc|sulphur|sulfur|caustic soda|frozen fish|tuna|chicken|milk powder)\b/i,
    not: /\b(catering|canteen|school meals|cleaning)\b/i },
  { id: "defence", en: "Defence & HLS", he: "ביטחוני",
    sectors: ["Defence & security"],
    kw: /\b(defen[cs]e|military|army|armed forces|navy|air force|police|gendarmerie|border|ammunition|munitions|cartridges?|weapons?|rifles?|armou?red|ballistic|body armou?r|helmets?|night vision|thermal camera|surveillance|radar|uav|drones?|counter-?drone|c4i|cctv|perimeter|explosive detect|bomb disposal|homeland security|hls|coast guard)\b/i },
  { id: "engineering", en: "Engineering & EPC", he: "הנדסה ו-EPC",
    sectors: ["Transport & civil infrastructure works", "Engineering & architecture services", "Water & wastewater", "Industrial & construction machinery"],
    kw: /\b(epc|turnkey|design[- ]and[- ]build|design, supply|supply and install|construction of|rehabilitation of|substation|pipeline|treatment plant|desalination|pumping station|bridge|railway|port|terminal|dam|irrigation|water supply system|sewer)\b/i },
  { id: "datacenters", en: "Data centers", he: "דאטא סנטרים",
    sectors: ["ICT & telecom"],
    kw: /\b(data ?cent(er|re)s?|server(s)?|ups|uninterruptible|precision (air|cooling)|crac|chillers?|racks?|switchgear|busway|gensets?|diesel generators?|fib(er|re) optic|colocation|cloud|hpc|storage area|san\b|nas\b|tier ?iii|tier ?iv|edge computing)\b/i },
  { id: "energy", en: "Energy & power", he: "אנרגיה וחשמל",
    sectors: ["Power & electrical equipment", "Energy, fuels & utilities"],
    kw: /\b(solar|photovoltaic|pv|wind|transformers?|substation|transmission line|distribution line|battery|bess|energy storage|hydro|grid|meters?|smart meter|switchgear|cables?|conductors?|power plant|generators?)\b/i },
  { id: "health", en: "Medical equipment", he: "ציוד רפואי",
    sectors: ["Healthcare & pharmaceuticals", "Scientific & measuring instruments"],
    kw: /\b(medical equipment|hospital equipment|imaging|x-?ray|ct scanner|mri|ultrasound|ventilators?|patient monitors?|laborator(y|ies)|analy[sz]ers?|dialysis|icu|operating theatre|sterili[sz]|incubators?|medical devices?|ppe|gloves|syringes?)\b/i,
    not: /\b(pharmaceutical|medicines?|drugs?|vaccines?)\b/i },
];

const mem: Record<string, { at: number; data: unknown }> = {};
async function csv(name: string): Promise<Row[]> {
  const hit = mem[name];
  if (hit && Date.now() - hit.at < 900_000) return hit.data as Row[];
  const r = await fetch(`${RAW}/${name}`, { cache: "no-store" }).catch(() => null);
  const rows = r && r.ok ? (Papa.parse<Row>(await r.text(), { header: true, skipEmptyLines: true }).data || []) : [];
  mem[name] = { at: Date.now(), data: rows };
  return rows;
}

const INTL = /^international|world bank|\(icb\)|\bicb\b|^global tender|open to foreign/i;
export type TItem = { id: string; t: string; b: string; c: string; s: string; v: number; dd: number | null; fit: number; d: string; acc: string; why: string; lensWhy?: string };
const item = (r: Row): TItem => ({ id: r.id, t: r.title_en || r.title_original || "", b: r.buyer || "", c: r.country || "", s: r.sector || "", v: num(r.est_value_usd),
  dd: r.days_left === "" || r.days_left == null ? null : num(r.days_left), fit: num(r.fit || r.score), d: r.decision || "", acc: r.access || "", why: r.fit_why || "" });

function lensMatch(l: Lens, r: Row): { sec: boolean; kw: boolean } {
  const text = `${r.title_en || ""} ${r.title_original || ""} ${r.commodity || ""}`;
  if (l.not && l.not.test(text)) return { sec: false, kw: false };
  return { sec: l.sectors.includes(r.sector || ""), kw: l.kw.test(text) };
}

export async function todayGeneral() {
  const { rows } = await allTenders();
  const open = rows.filter((r) => r.stage !== "planned");
  const newBig = open.filter((r) => r.new === "NEW" && INTL.test(r.access || "") && num(r.est_value_usd) >= 1_000_000 && num(r.fit || r.score) >= 40)
    .sort((a, b) => num(b.est_value_usd) - num(a.est_value_usd)).slice(0, 8).map(item);
  const closing = open.filter((r) => r.decision === "Pursue" && num(r.days_left) >= 2 && num(r.days_left) <= 10)
    .sort((a, b) => num(b.fit || b.score) - num(a.fit || a.score)).slice(0, 8).map(item);
  const plays = (await csv("plays.csv")).sort((a, b) => num(b.value_usd) - num(a.value_usd)).slice(0, 6);
  const news = (await csv("news.csv")).sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 10);
  const brief = (await csv("briefing_items.csv")).filter((x) => x.signal).sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 8);
  return {
    counts: { open: open.length, newToday: open.filter((r) => r.new === "NEW").length, intl: open.filter((r) => INTL.test(r.access || "")).length,
      pursue: open.filter((r) => r.decision === "Pursue").length, closingWeek: open.filter((r) => num(r.days_left) >= 0 && num(r.days_left) <= 7).length,
      planned: rows.length - open.length },
    newBig, closing, plays, news, brief,
  };
}

export async function todayFocus(lensId: string) {
  const l = LENSES.find((x) => x.id === lensId) || LENSES[0];
  const { rows } = await allTenders();
  const scored: { r: Row; sc: number; m: { sec: boolean; kw: boolean } }[] = [];
  for (const r of rows) {
    const m = lensMatch(l, r);
    if (!m.sec && !m.kw) continue;
    scored.push({ r, m, sc: num(r.fit || r.score) * (m.sec && m.kw ? 1.25 : 1) });
  }
  scored.sort((a, b) => b.sc - a.sc);
  const tag = (x: { r: Row; m: { sec: boolean; kw: boolean } }) => ({ ...item(x.r), lensWhy: x.m.sec && x.m.kw ? "sector and product" : x.m.sec ? "sector" : "product words" });
  const open = scored.filter((x) => x.r.stage !== "planned");
  const top = open.slice(0, 25).map(tag);
  const closing = open.filter((x) => num(x.r.days_left) >= 2 && num(x.r.days_left) <= 14).slice(0, 8).map(tag);
  const fresh = open.filter((x) => x.r.new === "NEW").slice(0, 8).map(tag);
  const planned = scored.filter((x) => x.r.stage === "planned").slice(0, 6).map(tag);
  const plays = (await csv("plays.csv")).filter((p) => l.sectors.includes(p.sector) || l.kw.test(`${p.title} ${p.thesis}`)).slice(0, 8);
  const countries = [...new Set(top.slice(0, 12).map((x) => x.c))].slice(0, 8);
  const news = (await csv("news.csv")).filter((n) => countries.includes(n.country) || l.kw.test(n.title || ""))
    .sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 10);
  const value = open.reduce((s, x) => s + num(x.r.est_value_usd), 0);
  return { lens: { id: l.id, en: l.en, he: l.he }, lenses: LENSES.map((x) => ({ id: x.id, en: x.en, he: x.he })),
    counts: { open: open.length, value, intl: open.filter((x) => INTL.test(x.r.access || "")).length, pursue: open.filter((x) => x.r.decision === "Pursue").length, countries: new Set(open.map((x) => x.r.country)).size },
    top, closing, fresh, planned, plays, news };
}
