import type { Supplier } from "@/lib/index";
import type { EvalQuery } from "@/lib/evalqueries";

// Blind relevance evaluation of the supplier search: one search result becomes two records. The labeller's record
// (rows file) says what was asked and who came back, with the evidence text the matcher read; the matcher's own
// verdict goes to a separate file keyed by (query id, rank), so a label is never influenced by the bucket.
// Pure functions (no I/O): the runner is tools/eval-suppliers.ts --blind, the scorer tools/eval_score.py.
export type BlindRow = { set: "product" | "tender"; query_id: string; query: string; rank: number; supplier: string; country: string; type: string;
  evidence: string; website: string; has_contact: boolean };
export type VerdictRow = { set: "product" | "tender"; query_id: string; rank: number; bucket: string; reason: string; evidence_basis: string;
  conflicts: string; gaps: string; kind: string; tier: string; match_version: string };
/** nothing the matcher concluded may appear in the labeller's file (tests/evalrows.test.ts) */
export const BLIND_KEYS = ["set", "query_id", "query", "rank", "supplier", "country", "type", "evidence", "website", "has_contact"] as const;
export const TOP = 25, EVIDENCE_MAX = 400;

const one = (v: unknown) => String(v ?? "").replace(/\s+/g, " ").trim();
/** The text classifyMatch reads, in its order of weight: the company's own words (products, industries, site
 *  title), what it supplied under contracts, customs headings and codes. Each part is capped so a long product list
 *  does not push the rest out; 400 characters in all. */
export function evidenceText(s: Partial<Supplier>): string {
  const parts: [string, unknown, number][] = [["products", s.p, 170], ["industries", s.in, 60], ["site title", s.wt, 60],
    ["supplied under contracts", s.sp, 110], ["customs headings", s.hd, 70], ["commodity tags", s.cm, 40], ["HS codes", s.hs, 40]];
  return parts.map(([k, v, n]) => { const t = one(v); return t ? `${k}: ${t.length > n ? t.slice(0, n - 3) + "..." : t}` : ""; })
    .filter(Boolean).join(" | ").slice(0, EVIDENCE_MAX);
}

/** Splits the grid supplierSearch returned (header row first, rows in the order the user sees them) into the blind
 *  rows and the verdicts. `record` finds the index record of a result (name, country), for the fields the grid does
 *  not carry (the site title); a web-found company has none and is described from the grid alone. */
export function splitResults(q: Pick<EvalQuery, "id" | "text"> & { set?: "product" | "tender" }, grid: string[][], record: (name: string, country: string) => Partial<Supplier> | undefined = () => undefined):
  { rows: BlindRow[]; verdicts: VerdictRow[] } {
  const [head, ...body] = grid.length ? grid : [[]];
  const ix = (k: string) => head.indexOf(k), g = (r: string[], k: string) => (ix(k) >= 0 ? one(r[ix(k)]) : "");
  const rows: BlindRow[] = [], verdicts: VerdictRow[] = [];
  body.slice(0, TOP).forEach((r, i) => {
    const name = g(r, "supplier"), country = g(r, "country"), rec = record(name, country);
    const fromGrid: Partial<Supplier> = { p: g(r, "products"), in: g(r, "industries"), sp: g(r, "supplied"), hd: g(r, "hs_names"), cm: g(r, "commodities"), hs: g(r, "hs_codes") };
    rows.push({ set: q.set || "product", query_id: q.id, query: q.text, rank: i + 1, supplier: name, country, type: g(r, "type"),
      evidence: evidenceText({ ...fromGrid, ...(rec ? { wt: rec.wt } : {}) }), website: g(r, "website"), has_contact: !!g(r, "directory_contact") });
    verdicts.push({ set: q.set || "product", query_id: q.id, rank: i + 1, bucket: g(r, "match"), reason: g(r, "match_why"), evidence_basis: g(r, "match_evidence"),
      conflicts: g(r, "match_conflicts"), gaps: g(r, "match_gaps"), kind: g(r, "kind"), tier: g(r, "tier"), match_version: g(r, "match_version") });
  });
  return { rows, verdicts };
}

// ---- the tender set: "suppliers for this tender" (panel.html showSuppliers -> /api/panel/suppliers-for) ----
// The system keeps no goods / works / services field on a tender; the nearest it has is the sector. The strata
// below are the harness's own reading of the title and sector, used only to pick a balanced sample: 10 clear goods
// purchases, 10 titles that buy no goods (works, services, consulting, development programmes: any supplier
// returned is a false positive), 10 mixed or vague ones. A labeller can overrule a stratum (rank 0 label).
export type Stratum = "goods" | "non_goods" | "mixed";
export type TenderLike = { id: string; title_en: string; commodity?: string; sector?: string; country?: string; region?: string; notice_type?: string; hs?: string; nature?: string };
const MIXED_RX = /\b(framework (agreement|contract)|lots?\b|supply(,| and) (delivery,? )?(installation|commissioning|construction)|supply, installation|design,? supply|supply and install\w*|turnkey|goods and services|works and supplies)\b/i;
const NONGOODS_RX = /\b(consult\w*|advisory|technical assistance|feasibility|stud(y|ies)|survey|audit\w*|training|capacity building|supervision|evaluation|development (programme|program|project|policy)|value chains?|resilience|governance|reform|construction of|rehabilitation of|repair of|civil works|road works|maintenance|servicing|cleaning services|security services|insurance|recruitment|rental|hire of|services? (for|of)|project$|program(me)?$)\b/i;
const GOODS_RX = /\b(supply of|supply and delivery of|purchase of|procurement of|acquisition of|delivery of|provision of)\b/i;
const BUYS_RX = /\b(suppl\w*|deliver\w*|purchase|procure\w*|acquisition|equipment)\b/i;
const WORKS_SECTOR = /works\b/i;
/** a development programme or project record (the owner's reported misses were on such titles) */
export const isProgramme = (t: TenderLike) => /^project\b/i.test(one(t.notice_type));
export function stratumOf(t: TenderLike, serviceSectors: Set<string>): Stratum | "" {
  const title = one(t.title_en), sector = one(t.sector);
  if (title.length < 15) return "";
  const nonGoodsSector = serviceSectors.has(sector) || WORKS_SECTOR.test(sector) || isProgramme(t);
  const nonGoodsTitle = NONGOODS_RX.test(title);
  if (MIXED_RX.test(title) && !(nonGoodsTitle && nonGoodsSector && !BUYS_RX.test(title))) return "mixed";
  if ((nonGoodsTitle || isProgramme(t)) && nonGoodsSector && !BUYS_RX.test(title)) return "non_goods";
  if (GOODS_RX.test(title) && !nonGoodsTitle && !nonGoodsSector && !/\binstall\w*/i.test(title)) return "goods";
  return "";
}
/** stable 32-bit hash (FNV-1a): the sample is the same for the same tender data, without favouring a source */
const fnv = (s: string) => { let h = 0x811c9dc5; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); } return h >>> 0; };
export function pickTenders<T extends TenderLike>(all: T[], serviceSectors: Set<string>, perStratum = 10, perSector = 3): { t: T; stratum: Stratum }[] {
  const out: { t: T; stratum: Stratum }[] = [];
  const pool = all.map((t) => ({ t, stratum: stratumOf(t, serviceSectors), h: fnv(String(t.id)) })).filter((x) => x.stratum).sort((a, b) => a.h - b.h || String(a.t.id).localeCompare(String(b.t.id)));
  for (const st of ["goods", "non_goods", "mixed"] as Stratum[]) {
    const mine = pool.filter((x) => x.stratum === st), bySector = new Map<string, number>(), got: typeof mine = [];
    // up to 4 of the 10 non-goods titles are development programmes, when the data has them
    if (st === "non_goods") got.push(...mine.filter((x) => isProgramme(x.t)).slice(0, Math.min(4, perStratum)));
    for (const x of mine) { if (got.length >= perStratum) break; if (got.includes(x) || (st === "non_goods" && isProgramme(x.t))) continue; const k = one(x.t.sector); if ((bySector.get(k) || 0) >= perSector) continue; bySector.set(k, (bySector.get(k) || 0) + 1); got.push(x); }
    for (const x of mine) { if (got.length >= perStratum) break; if (!got.includes(x)) got.push(x); }   // too few sectors: fill up
    out.push(...got.map((x) => ({ t: x.t, stratum: st })));
  }
  return out;
}
/** the request the tender screen sends for one tender (the same fields and the same text as panel.html) */
export const tenderRequest = (t: TenderLike) => ({ sector: one(t.sector), text: `${t.title_en || ""} ${t.commodity || ""}`.slice(0, 600), country: one(t.country), region: one(t.region), hs: one(t.hs), n: TOP,
  // read by the search only when TENDER_KIND=on (lib/panel.ts tenderPlan)
  tender: { title: one(t.title_en).slice(0, 300), category: one(t.nature) } });

/** The only numbers a public workflow log may show: counts, never a supplier. */
export function summarize(perQuery: { id: string; returned: number; total: number; ms: number; error?: string }[], verdicts: VerdictRow[], extra: Record<string, unknown> = {}) {
  const buckets: Record<string, number> = {};
  for (const v of verdicts) buckets[v.bucket || "none"] = (buckets[v.bucket || "none"] || 0) + 1;
  return { queries_run: perQuery.length, rows_returned: verdicts.length, rows_per_bucket: buckets,
    queries_under_5_rows: perQuery.filter((x) => x.returned < 5).length, queries_with_no_rows: perQuery.filter((x) => !x.returned).length,
    queries_failed: perQuery.filter((x) => x.error).length, ...extra, per_query: perQuery };
}
