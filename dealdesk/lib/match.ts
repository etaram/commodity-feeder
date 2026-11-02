import { tenders, type Tender } from "./index";
import type { Profile } from "./profiles";

// Personal fit score (0-100) for every open tender, from the user's profile. Plain code, no AI, so it costs nothing
// and runs on every request. Weights (see the product spec): product 35, place 15, eligibility 15, value 10,
// timing 10, engine score 15. Each match carries a short "why" built from the parts that scored.
export type Match = {
  id: string; score: number; why: string[]; t: string; b: string; c: string; rg: string; s: string; v: number | null;
  dl: string; dd: number | null; l: string; src: string; st: string; rt: string; d: string;
};

const money = (n: number) => (n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`);

export function scoreTender(r: Tender, p: Profile): { score: number; why: string[]; product: boolean } {
  const why: string[] = [];
  const title = (r.t || "").toLowerCase();

  // product (35)
  let prod = 0;
  const kw = p.keywords.find((k) => k.length > 1 && title.includes(k));
  if (p.sectors.includes(r.s)) { prod += 25; why.push(r.s); }
  if (r.g && p.groups.includes(r.g)) { prod += 25; if (!why.length) why.push(r.g); }
  if (kw) { prod += 15; why.push(`"${kw}"`); }
  prod = Math.min(35, prod);
  const anyProduct = p.sectors.length + p.groups.length + p.keywords.length > 0;
  if (!anyProduct) prod = 15;

  // place (15)
  let place = 0;
  if (p.countries.includes(r.c)) { place = 15; why.push(r.c); }
  else if (p.regions.includes(r.rg)) { place = 10; why.push(r.rg); }
  else if (!p.countries.length && !p.regions.length) place = 8;

  // eligibility (15)
  const partner = p.partners.includes(r.c);
  const elig: Record<string, number> = { direct: 15, "sub-supply to the winner": 10, "via local partner": partner ? 13 : 6, "needs local partner": partner ? 11 : 3 };
  let el = r.rt ? elig[r.rt] ?? 8 : 8;
  if (r.acc === "set-aside") el = 0;
  if (r.acc === "intl") el = Math.min(15, el + 3);
  if (partner && (r.rt === "via local partner" || r.rt === "needs local partner")) why.push("יש שותף מקומי");
  else if (r.rt === "direct") why.push("פתוח להגשה ישירה");

  // value (10)
  let val = 5;
  if (r.v) {
    const lo = p.valueMin ?? 0, hi = p.valueMax ?? Infinity;
    val = r.v >= lo && r.v <= hi ? 10 : r.v < lo ? 2 : 4;
    if (val === 10) why.push(money(r.v));
  }

  // timing (10)
  let time = 5;
  if (r.st === "planned") { time = 8; why.push("מכרז עתידי"); }
  else if (r.dd !== null && r.dd !== undefined) {
    time = r.dd < 7 ? 1 : r.dd <= 60 ? 10 : 7;
    if (r.dd >= 7 && r.dd <= 60) why.push(`${r.dd} ימים להגשה`);
  }

  // engine (15): the deal engine's own score (margin, competition, buyer history)
  const eng = Math.round(((r.sc ?? 40) / 100) * 15);

  return { score: Math.max(0, Math.min(100, prod + place + el + val + time + eng)), why: why.slice(0, 5), product: prod >= 15 && anyProduct };
}

export async function matches(p: Profile, opts: { mode?: "focus" | "broad"; limit?: number; ids?: string[] } = {}) {
  const all = await tenders();
  const mode = opts.mode || p.mode;
  const hidden = new Set(p.hidden), excluded = new Set(p.excluded);
  const only = opts.ids ? new Set(opts.ids) : null;
  const out: Match[] = [];
  for (const r of all) {
    if (hidden.has(r.id) || excluded.has(r.c) || (only && !only.has(r.id))) continue;
    const m = scoreTender(r, p);
    if (!only && mode === "focus" && (!m.product || m.score < p.minScore)) continue;
    if (!only && mode === "broad" && m.score < 35) continue;
    out.push({ id: r.id, score: m.score, why: m.why, t: r.t, b: r.b, c: r.c, rg: r.rg, s: r.s, v: r.v, dl: r.dl, dd: r.dd, l: r.l, src: r.src, st: r.st, rt: r.rt, d: r.d });
  }
  out.sort((a, b) => b.score - a.score || (a.dd ?? 999) - (b.dd ?? 999));
  return { total: out.length, items: out.slice(0, Math.min(500, opts.limit || 150)) };
}

// For the onboarding form: the sectors, groups, regions and countries that actually occur, with counts.
export async function facets() {
  const all = await tenders();
  const count = (get: (r: Tender) => string) => {
    const m = new Map<string, number>();
    for (const r of all) { const v = get(r); if (v) m.set(v, (m.get(v) || 0) + 1); }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  };
  return { total: all.length, sectors: count((r) => r.s), groups: count((r) => r.g), regions: count((r) => r.rg), countries: count((r) => r.c).slice(0, 200) };
}
