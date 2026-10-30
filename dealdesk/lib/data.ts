import Papa from "papaparse";

const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main";
const TTL = 900;

export type Row = Record<string, string>;

async function csv(path: string, revalidate = TTL): Promise<Row[]> {
  try {
    const r = await fetch(`${RAW}/${path}`, { next: { revalidate } });
    if (!r.ok) return [];
    const text = await r.text();
    const out = Papa.parse<Row>(text, { header: true, skipEmptyLines: true });
    return (out.data || []).filter((x) => Object.values(x).some(Boolean));
  } catch {
    return [];
  }
}

export const num = (v: string | undefined) => {
  const n = parseFloat(v || "");
  return Number.isFinite(n) ? n : 0;
};

export const usd = (v: number) =>
  v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${Math.round(v)}`;

export const pct = (v: string | undefined, digits = 0) => {
  const n = parseFloat(v || "");
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "-";
};

export const getDeals = () => csv("data/leads/deal_calc.csv");
export const getPress = () => csv("data/leads/press.csv");
export const getIsrael = () => csv("data/israel/items.csv");
export const getCountries = () => csv("data/leads/countries.csv");
export const getSectors = () => csv("data/leads/sectors.csv");
export const getSources = () => csv("data/leads/status.csv");
export const getTrends = () => csv("data/leads/price_trends.csv");
export const getBuyers = () => csv("data/leads/buyers.csv");
export const getAwards = () => csv("data/leads/awards.csv");
export const getGrants = () => csv("data/leads/grants.csv");
export const getExempt = () => csv("data/leads/exempt.csv");
export const getIlExempt = () => csv("data/leads/il_exempt.csv");
export const getGovernance = () => csv("data/leads/governance.csv");

export async function getDeal(id: string): Promise<Row | undefined> {
  const deals = await getDeals();
  return deals.find((d) => d.id === id);
}

export const ROUTE_LABEL: Record<string, string> = {
  direct: "Direct bid",
  "via local partner": "Via local partner",
  "needs local partner": "Needs a local partner",
  "sub-supply to the winner": "Sub-supply to the winner",
};
