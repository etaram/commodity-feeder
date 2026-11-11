// Supplier-search evaluation on the real supplier index, through the code the product runs (lib/panel.ts supplierSearch).
//
//   node ev.js --blind <dir>      the blind relevance run (workflow supplier-eval). Writes into <dir>:
//       rows.jsonl          one line per returned supplier, top 25 per request in the order the user sees them;
//                           no bucket, no reason: this is the file the labeller reads
//       verdicts.jsonl      the matcher's bucket and reason, keyed by (set, query_id, rank)
//       tenders.jsonl       the tender set: tender id, title, sector, stratum and what the search derived from the title
//       human_labels.jsonl  the owner's own verdicts ('Verified capabilities', method "human report"), ground truth
//       summary.json        counts only; the only thing printed (the repository and its logs are public)
//     Two sets: "product" = the 40 buyer requests of lib/evalqueries.ts EVAL_SET, searched as the supplier research
//     screen does (strict, like panel.html DD_SUPSEARCH); "tender" = 30 open tenders picked at run time from the
//     app's own tender store, searched as the tender screen does (sector, title + commodity, country, region; not strict).
//   node ev.js <file.json>        the older sheet benchmark (leads/search_eval.py writes it to the tab 'Search eval').
//
// Scoring: tools/eval_score.py. Labelling guide: docs/release-2026-11-13/SUPPLIER_MATCH_LABELLING.md
import { mkdirSync, writeFileSync } from "fs";
import path from "path";
import { allTenders, plainConceptWords, queryWords, supplierSearch } from "@/lib/panel";
import { suppliers as supplierIndex, type Supplier } from "@/lib/index";
import { detectCommodity } from "@/lib/commodity";
import { SERVICE_SECTOR } from "@/lib/supfit";
import { dedupeKey } from "@/lib/supmatch";
import { readRanges, UNIVERSE } from "@/lib/sheets";
import { EVAL_SET, QUERIES } from "@/lib/evalqueries";
import { pickTenders, splitResults, summarize, tenderRequest, type BlindRow, type TenderLike, type VerdictRow } from "@/lib/evalrows";
export { QUERIES };

const say = (s: string) => process.stdout.write(s + "\n");

/** How supplierSearch reads a request text (it has three routes; the tender route is almost always the last one). */
function derivation(text: string) {
  const short = text.trim().length <= 80;
  const cmd = short ? detectCommodity(text) : null;
  const modelOn = !!process.env.ANTHROPIC_API_KEY && process.env.SUPPLIER_EXPAND !== "off";
  const words = queryWords(text), concepts = plainConceptWords(words);
  if (cmd) return { route: "commodity table", terms: [cmd.key], concepts: 1 };
  if (short && modelOn) return { route: "model expansion (terms not exposed by the search)", terms: [] as string[], concepts: 0 };
  return { route: "title words", terms: concepts, concepts: concepts.length };
}

async function blind(dir: string) {
  // nothing a library prints may reach the public log: only the counts written at the end do
  for (const k of ["log", "info", "warn", "error", "debug"] as const) console[k] = () => undefined;
  mkdirSync(dir, { recursive: true });
  const ix = await supplierIndex();
  if (ix.error && !ix.rows.length) throw new Error(`supplier index not readable: ${ix.error}`);
  const byKey = new Map<string, Supplier>();
  for (const s of ix.rows) { const k = dedupeKey(s); if (!byKey.has(k) || s.wt) byKey.set(k, s); }
  const record = (name: string, country: string) => byKey.get(dedupeKey({ n: name, c: country } as Supplier));
  const rows: BlindRow[] = [], verdicts: VerdictRow[] = [];
  type PQ = { id: string; returned: number; total: number; ms: number; error?: string };
  const product: PQ[] = [], tender: (PQ & { stratum: string })[] = [], tenderMeta: Record<string, unknown>[] = [];

  for (const q of EVAL_SET) {
    const t0 = Date.now();
    try {
      const r = await supplierSearch({ text: q.text, n: 25, strict: true });
      const x = splitResults({ ...q, set: "product" }, r.values, record);
      rows.push(...x.rows); verdicts.push(...x.verdicts);
      product.push({ id: q.id, returned: x.rows.length, total: r.total, ms: Date.now() - t0 });
    } catch (e) { product.push({ id: q.id, returned: 0, total: 0, ms: Date.now() - t0, error: String(e).slice(0, 80) }); }
  }

  let tenderError = "", tendersOpen = 0;
  try {
    const store = await allTenders();
    tendersOpen = store.rows.length;
    const picked = pickTenders(store.rows as unknown as TenderLike[], SERVICE_SECTOR);
    let i = 0;
    for (const { t, stratum } of picked) {
      const id = `T${String(++i).padStart(2, "0")}`, req = tenderRequest(t), t0 = Date.now();
      const meta: Record<string, unknown> = { set: "tender", query_id: id, tender_id: t.id, title: t.title_en, commodity: t.commodity || "", sector: t.sector || "",
        notice_type: t.notice_type || "", country: t.country || "", stratum,
        // the system has no goods / works / services field on a tender: the sector is all it knows, and the search does not use it to decide whether goods are bought at all
        system_goods_class: "none (the system does not classify a tender as goods, works or services)",
        sector_is_service_or_works: SERVICE_SECTOR.has(String(t.sector || "")) || /works\b/i.test(String(t.sector || "")),
        request_text: req.text, derivation: derivation(req.text), match_rule: "not strict: a supplier is returned when any one derived term matches, or on the sector alone when no term was derived" };
      try {
        const r = await supplierSearch({ ...req, originRegion: "", originCountry: "", exportersOnly: false, kind: "", strict: false });
        const x = splitResults({ id, text: req.text.trim(), set: "tender" }, r.values, record);
        rows.push(...x.rows); verdicts.push(...x.verdicts);
        tender.push({ id, stratum, returned: x.rows.length, total: r.total, ms: Date.now() - t0 });
        tenderMeta.push({ ...meta, derived_query: r.query, returned: x.rows.length, total_matched: r.total });
      } catch (e) { tender.push({ id, stratum, returned: 0, total: 0, ms: Date.now() - t0, error: String(e).slice(0, 80) }); tenderMeta.push({ ...meta, error: String(e).slice(0, 80) }); }
    }
  } catch (e) { tenderError = String(e).slice(0, 80); }

  // the owner's own verdicts: ground truth for the scorer. The method cell names the person; only its kind is kept.
  let human: Record<string, string>[] = [], humanError = "";
  try {
    const g = (await readRanges(UNIVERSE, ["'Verified capabilities'!A1:I20000"]))?.[0] || [];
    const h = (g[0] || []).map((x) => String(x).toLowerCase()), c = (r: string[], k: string) => String(r[h.indexOf(k)] ?? "").trim();
    human = g.slice(1).filter((r) => /^human report/i.test(c(r, "method"))).map((r) => ({ supplier: c(r, "supplier"), country: c(r, "country"), product: c(r, "product"),
      label: c(r, "label").toLowerCase(), asked: c(r, "source_query"), checked: c(r, "checked"), note: c(r, "evidence_note") }));
  } catch (e) { humanError = String(e).slice(0, 80); }

  const jl = (a: unknown[]) => a.map((x) => JSON.stringify(x)).join("\n") + (a.length ? "\n" : "");
  const tv = verdicts.filter((v) => v.set === "tender"), nonGoods = tender.filter((x) => x.stratum === "non_goods");
  const summary = {
    at: new Date().toISOString(), index_size: ix.rows.length, index_searchable: ix.rows.filter((r) => r.tr === "1" || r.tr === "2" || r.tr === "3").length,
    model_expansion: !!process.env.ANTHROPIC_API_KEY && process.env.SUPPLIER_EXPAND !== "off", reviewed_facts_applied: process.env.SUPPLIER_VERIFIED !== "off",
    data_source: process.env.DATA_BASE_URL ? "DATA_BASE_URL" : "public repository (default)",
    product: summarize(product, verdicts.filter((v) => v.set === "product")),
    tender: { ...summarize(tender, tv), tenders_open: tendersOpen, picked_per_stratum: Object.fromEntries(["goods", "non_goods", "mixed"].map((s) => [s, tender.filter((x) => x.stratum === s).length])),
      non_goods_tenders_with_any_supplier: nonGoods.filter((x) => x.returned > 0).length, non_goods_tenders: nonGoods.length, ...(tenderError ? { error: tenderError } : {}) },
    human_labels: { rows: human.length, ...(humanError ? { error: humanError } : {}) },
  };
  writeFileSync(path.join(dir, "rows.jsonl"), jl(rows));
  writeFileSync(path.join(dir, "verdicts.jsonl"), jl(verdicts));
  writeFileSync(path.join(dir, "tenders.jsonl"), jl(tenderMeta));
  writeFileSync(path.join(dir, "human_labels.jsonl"), jl(human));
  writeFileSync(path.join(dir, "summary.json"), JSON.stringify(summary, null, 1));
  // the log: counts only
  const line = (name: string, s: ReturnType<typeof summarize>) => say(`${name}: requests run ${s.queries_run}, rows returned ${s.rows_returned}, per bucket ${JSON.stringify(s.rows_per_bucket)}, ` +
    `requests with fewer than 5 rows ${s.queries_under_5_rows} (no rows ${s.queries_with_no_rows}), failed ${s.queries_failed}`);
  say(`index size ${summary.index_size} (searchable tiers 1-3: ${summary.index_searchable}); model expansion ${summary.model_expansion ? "on" : "off"}; reviewed facts ${summary.reviewed_facts_applied ? "applied" : "off"}; data from ${summary.data_source}`);
  line("product set", summary.product);
  line("tender set", summary.tender);
  say(`tender set: open tenders ${tendersOpen}, picked ${JSON.stringify(summary.tender.picked_per_stratum)}, non-goods tenders that got any supplier ${summary.tender.non_goods_tenders_with_any_supplier} of ${summary.tender.non_goods_tenders}${tenderError ? "; TENDER SET FAILED" : ""}`);
  say(`owner verdicts exported: ${human.length}${humanError ? " (READ FAILED)" : ""}`);
  if (!rows.length) throw new Error("no rows returned for any request");
}

async function sheetBenchmark(file: string) {
  const out: Record<string, unknown>[] = [];
  for (const q of QUERIES) {
    const t0 = Date.now();
    const r = await supplierSearch({ text: q, n: 15, strict: true }); // the same mode as the supplier research screen
    const [head, ...rows] = r.values;
    const ix = (k: string) => (head as string[]).indexOf(k);
    rows.forEach((row, i) => out.push({ query: q, rank: i + 1, total: r.total, ms: Date.now() - t0,
      supplier: row[ix("supplier")], country: row[ix("country")], tier: row[ix("tier")], kind: row[ix("kind")],
      main_sector: row[ix("main_sector")], match: ix("match") >= 0 ? row[ix("match")] : "", evidence: ix("match_evidence") >= 0 ? row[ix("match_evidence")] : "",
      conflicts: ix("match_conflicts") >= 0 ? row[ix("match_conflicts")] : "", gaps: ix("match_gaps") >= 0 ? row[ix("match_gaps")] : "",
      products: String(row[ix("products")] || row[ix("supplied")] || row[ix("hs_names")] || "").slice(0, 160) }));
    if (!rows.length) out.push({ query: q, rank: 0, total: r.total, ms: Date.now() - t0 });
    console.log(`${q}: ${r.total} results, ${Date.now() - t0} ms`);
  }
  writeFileSync(file, JSON.stringify(out));
}

const a = process.argv.slice(2);
(a[0] === "--blind" ? blind(a[1] || "eval-out") : sheetBenchmark(a[0] || "eval.json"))
  // an error text can quote data: in the blind run only its first 80 characters are shown
  .then(() => process.exit(0), (e) => { process.stderr.write(`evaluation failed: ${String(e).slice(0, a[0] === "--blind" ? 80 : 2000)}\n`); process.exit(1); });
