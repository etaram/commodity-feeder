import Papa from "papaparse";

// Financing and grants: who can finance, insure or grant-fund a cross-border supply deal.
// Source: data/finance/finance_providers.csv, every row checked on the institution's official site (README there).
// Matching rules for one deal (a tender or a deal in the workspace):
// - an export credit agency covers its own country's exports: it fits when a candidate supplier comes from its
//   country (ASHRA always, as Sinder is Israeli);
// - development banks, multilateral programs, insurers, banks and funds fit by the buyer's region and the sector;
// - grants fit by sector and region (project preparation, feasibility);
// - defence goods: an institution whose policy excludes defence is left out, one that states it finances defence
//   ranks first; a deal larger than the stated maximum is flagged, not hidden;
// - institutions whose rules exclude Israeli firms (boycott clauses) are flagged.
const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/finance/finance_providers.csv";
export type Fin = Record<string, string>;
let mem: { at: number; rows: Fin[] } | null = null;

export async function providers(): Promise<Fin[]> {
  if (mem && Date.now() - mem.at < 3_600_000) return mem.rows;
  const r = await fetch(RAW, { cache: "no-store" }).catch(() => null);
  const rows = r && r.ok ? (Papa.parse<Fin>(await r.text(), { header: true, skipEmptyLines: true }).data || []) : [];
  mem = { at: Date.now(), rows };
  return rows;
}

const list = (v: string) => String(v || "").split(";").map((x) => x.trim()).filter(Boolean);
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/[,$]/g, "")); return Number.isFinite(n) ? n : 0; };
const BOYCOTT = /boycott|not eligible for israel|excludes israel/i;
const REP: Record<string, number> = { multilateral: 5, ECA: 4, DFI: 4, insurer: 3, grant: 3, bank: 2, fund: 1 };

export function israelBlocked(f: Fin) { return BOYCOTT.test(`${f.eligibility} ${f.israel_link} ${f.content_rule}`); }
export function reputation(f: Fin) {
  // a factual proxy, never a judgement: public owner and a published credit rating count, then the category
  let s = REP[f.category] || 1;
  if (f.owner === "multilateral" || f.owner === "government") s += 2;
  if (/AAA/.test(f.rating)) s += 3; else if (/AA/.test(f.rating)) s += 2; else if (f.rating) s += 1;
  if (/berne union|oecd/i.test(f.reputation_note)) s += 1;
  return s;
}

export type FinQuery = { sector?: string; region?: string; buyerCountry?: string; origins?: string[]; value?: number; defence?: boolean };
export async function financeFor(q: FinQuery) {
  const rows = await providers();
  const origins = new Set([...(q.origins || []), "ISR"]);
  const out: { f: Fin; sc: number; why: string[]; flags: string[] }[] = [];
  for (const f of rows) {
    const sectors = list(f.sectors), regions = list(f.regions);
    const secOk = !q.sector || sectors.includes("all") || sectors.includes(q.sector);
    const regOk = !q.region || regions.includes("global") || regions.includes(q.region);
    const why: string[] = [], flags: string[] = [];
    let sc = 0;
    if (f.category === "ECA") {
      if (!origins.has(f.country_hq)) continue;
      sc += 6; why.push(f.country_hq === "ISR" ? "Israeli export credit agency" : `covers exports from ${f.country_hq}`);
    } else {
      if (!regOk || !secOk) continue;
      sc += regions.includes(q.region || "") ? 3 : 1; why.push(regions.includes(q.region || "") ? `active in ${q.region}` : "global");
      if (q.sector && sectors.includes(q.sector)) { sc += 2; why.push("sector"); }
    }
    if (q.defence) {
      if (f.defence_ok === "no") continue;
      if (f.defence_ok === "yes") { sc += 3; why.push("states it finances defence"); }
      else if (f.defence_ok === "case by case") why.push("defence case by case");
      else flags.push("defence policy not stated: ask first");
    }
    const max = num(f.ticket_max_usd), min = num(f.ticket_min_usd);
    if (q.value && max && q.value > max) flags.push("deal above the stated maximum");
    if (q.value && min && q.value < min) flags.push("deal below the stated minimum");
    if (israelBlocked(f)) flags.push("rules exclude Israeli firms");
    sc += reputation(f) / 2;
    out.push({ f, sc, why, flags });
  }
  out.sort((a, b) => (a.flags.includes("rules exclude Israeli firms") ? 1 : 0) - (b.flags.includes("rules exclude Israeli firms") ? 1 : 0) || b.sc - a.sc);
  // eligibility is never assumed from a regional tag (spec phase 5): each suggestion says how strong its basis is
  // and what must be confirmed before it can carry a deal
  const conditions = (f: Fin) => [
    "applicant or borrower type (exporter, buyer, bank)", "amount within the ticket range", "tenor and repayment",
    ...(f.content_rule && !/^(none stated|not stated)$/i.test(f.content_rule) ? [`content rule: ${f.content_rule}`] : []),
    ...(q.defence ? ["defence goods accepted"] : []), "eligible goods and destination (sanctions, country cover)"];
  return out.slice(0, 12).map((x) => {
    const basis = x.f.category === "ECA" && origins.has(x.f.country_hq) ? "conditional" : x.why.includes("sector") ? "plausible" : "directory";
    const basis_note = basis === "conditional" ? `conditional: it covers exports from ${x.f.country_hq}; eligibility to confirm` : basis === "plausible" ? "plausible: active in this region and sector; eligibility to confirm" : "directory entry: active in the region; no evidence it finances this kind of deal";
    return { ...pick(x.f), why: x.why, flags: x.flags, basis, basis_note, conditions: conditions(x.f) };
  });
}

const KEEP = ["name", "short_name", "category", "country_hq", "owner", "products", "sectors", "regions", "eligibility", "content_rule", "defence_ok",
  "ticket_min_usd", "ticket_max_usd", "typical_cost", "rating", "reputation_note", "israel_link", "apply_url", "source_url", "verified", "check_note"];
const pick = (f: Fin) => Object.fromEntries(KEEP.map((k) => [k, f[k] || ""]));

export async function financeList() {
  const rows = await providers();
  return rows.map((f) => ({ ...pick(f), rep: reputation(f), israel_blocked: israelBlocked(f) }));
}
