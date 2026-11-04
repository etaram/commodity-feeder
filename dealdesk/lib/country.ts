import Papa from "papaparse";
import { tenders as tenderIndex, type Tender } from "@/lib/index";

const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data";
const mem: Record<string, { at: number; data: unknown }> = {};
async function cached<T>(name: string, ttlMs: number, make: () => Promise<T>): Promise<T> {
  const hit = mem[name];
  if (hit && Date.now() - hit.at < ttlMs) return hit.data as T;
  const data = await make();
  mem[name] = { at: Date.now(), data };
  return data;
}

// Country intelligence: one page from the same layers the brain uses (BRAIN.md). Public CSVs and the tender
// index only; nothing private, nothing sent anywhere. Numbers are counts and sums of what the sources state.
type Row = Record<string, string>;
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/[,$]/g, "")); return Number.isFinite(n) ? n : 0; };

async function csv(path: string): Promise<Row[]> {
  return cached(`csvobj-${path}`, 900_000, async () => {
    const r = await fetch(`${RAW}/${path}`, { cache: "no-store" });
    if (!r.ok) return [];
    return (Papa.parse<Row>(await r.text(), { header: true, skipEmptyLines: true }).data || []) as Row[];
  });
}

export async function countryIntel(iso: string) {
  const c = iso.toUpperCase().slice(0, 3);
  const [countries, competition, buyers, winners, markets, plays, news, risk, gov, all, wbPlans, wbAwards, groups] = await Promise.all([
    csv("leads/countries.csv"), csv("leads/competition.csv"), csv("leads/buyers.csv"), csv("leads/competitors.csv"),
    csv("leads/markets.csv"), csv("leads/plays.csv"), csv("leads/news.csv"), csv("leads/country_risk.csv"), csv("leads/governance.csv"), tenderIndex(),
    csv("leads/wb_plans.csv"), csv("leads/wb_awards.csv"), csv("leads/groups_lei.csv"),
  ]);
  const parent = new Map(groups.map((g) => [g.company.toLowerCase(), g.parent_name && g.parent_name !== g.legal_name ? g.parent_name : ""]));
  const open = all.filter((t: Tender) => t.c === c);
  const live = open.filter((t) => t.st !== "planned"), planned = open.filter((t) => t.st === "planned");
  const bySector = new Map<string, { n: number; usd: number; intl: number; pursue: number }>();
  for (const t of live) {
    const s = bySector.get(t.s) || { n: 0, usd: 0, intl: 0, pursue: 0 };
    s.n++; s.usd += t.v || 0; if (t.acc === "intl") s.intl++; if (t.d === "Pursue") s.pursue++;
    bySector.set(t.s, s);
  }
  const sectors = [...bySector.entries()].map(([sector, v]) => ({ sector, ...v })).sort((a, b) => b.usd - a.usd || b.n - a.n).slice(0, 10);
  const top = [...live].sort((a, b) => (b.sc || 0) - (a.sc || 0)).slice(0, 12);
  const topPlanned = [...planned].sort((a, b) => (b.v || 0) - (a.v || 0)).slice(0, 8);
  const comp = competition.filter((r) => r.country === c).sort((a, b) => num(b.awards_12m) - num(a.awards_12m)).slice(0, 10);
  const awards = comp.reduce((a, r) => a + num(r.awards_12m), 0), fwins = comp.reduce((a, r) => a + num(r.foreign_wins), 0);
  const topBuyers = buyers.filter((r) => r.country === c).sort((a, b) => num(b.total_usd) - num(a.total_usd)).slice(0, 10)
    .map((r) => ({ buyer: r.buyer, sector: r.group, awards_12m: r.awards_12m, total_usd: r.total_usd, next_expected: r.next_expected, suppliers: (r.current_suppliers || "").slice(0, 160), link: r.last_notice }));
  const topWinners = winners.filter((r) => (r.buyer_countries || "").split(" ").includes(c)).sort((a, b) => num(b.won_usd_est) - num(a.won_usd_est)).slice(0, 10)
    .map((r) => ({ winner: r.supplier, from: r.supplier_country, sector: r.group, wins_12m: r.wins_12m, won_usd: r.won_usd_est, foreign: r.supplier_country !== c, group: parent.get(String(r.supplier || "").toLowerCase()) || "" }));
  const plansHere = wbPlans.filter((r) => r.country === c).slice(0, 10).map((r) => ({ date: r.date, project_id: r.project_id, title: r.title, pdf: r.pdf, link: r.link }));
  const wbWin = new Map<string, { n: number; usd: number; from: string }>();
  for (const a of wbAwards.filter((r) => r.country === c)) { const k = a.supplier; const v = wbWin.get(k) || { n: 0, usd: 0, from: a.supplier_country }; v.n++; v.usd += num(a.usd); wbWin.set(k, v); }
  const wbWinners = [...wbWin.entries()].map(([supplier, v]) => ({ supplier, ...v })).sort((a, b) => b.usd - a.usd).slice(0, 8);
  const imports = markets.filter((r) => r.iso3 === c).sort((a, b) => num(b.imports_usd) - num(a.imports_usd)).slice(0, 12)
    .map((r) => ({ product: r.product, hs: r.hs6, group: r.group, usd: r.imports_usd, growth: r.growth_pct, unit: r.unit_value_usd_kg, bench: r.benchmark_usd_kg, premium: r.premium_vs_benchmark_pct, year: r.year }));
  const cp = plays.filter((r) => r.country === c).slice(0, 12);
  const cn = news.filter((r) => r.country === c).slice(0, 20);
  const meta = countries.find((r) => r.country === c) || {};
  const g = gov.find((r) => r.country === c) || {};
  const rk = risk.find((r) => r.iso3 === c);
  return {
    ok: true, country: c, region: live[0]?.rg || planned[0]?.rg || "",
    open: live.length, open_usd: live.reduce((a, t) => a + (t.v || 0), 0), intl: live.filter((t) => t.acc === "intl").length,
    pursue: live.filter((t) => t.d === "Pursue").length, planned: planned.length, planned_usd: planned.reduce((a, t) => a + (t.v || 0), 0),
    sources: String(meta.sources || "").split(";").map((s) => s.trim()).filter(Boolean).slice(0, 12),
    sectors, top, topPlanned, competition: comp, awards_12m: awards, foreign_win_rate: awards ? fwins / awards : null,
    buyers: topBuyers, winners: topWinners, imports, plays: cp, news: cn, wb_plans: plansHere, wb_winners: wbWinners,
    integrity: g.integrity_score ? { score: g.integrity_score, flag: g.flag, advice: g.advice, single_bid_share: g.single_bid_share } : null,
    risk: rk ? { level: rk.level, reason: rk.reason } : null,
  };
}
