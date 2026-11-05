// Supplier-search benchmark: runs the live search code on the real supplier index for a fixed query set and writes
// the top results (with match bucket, evidence, conflicts and gaps) to a JSON file. No model calls
// (SUPPLIER_EXPAND=off), so the run is cheap and repeatable. Labels are human: the sheet tab "Search eval" has a
// "label" column; tools/eval_labels.py computes supported precision@5/@10 from it.
import { writeFileSync } from "fs";
import { supplierSearch } from "@/lib/panel";

import { QUERIES } from "@/lib/evalqueries";
export { QUERIES };

async function main() {
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
  writeFileSync(process.argv[2] || "eval.json", JSON.stringify(out));
}
main().catch((e) => { console.error(e); process.exit(1); });
