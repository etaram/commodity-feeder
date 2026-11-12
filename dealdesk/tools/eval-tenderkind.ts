// Scores the tender classifier (lib/tenderkind.ts) against the blind labeller's strata, without showing a title.
//
//   cd dealdesk && npx --yes esbuild@0.24.0 tools/eval-tenderkind.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=/tmp/tk.js --log-level=error
//   node /tmp/tk.js <tenders.jsonl> <labels.jsonl> --ids T02,T03,T05 [--detail] [--jsonl=<file>]
//
// tenders.jsonl  as tools/eval-suppliers.ts --blind writes it: query_id, title, sector and (newer runs) nature
// labels.jsonl   the labeller's file: a line with rank 0 and label goods / non_goods / mixed is the stratum of that tender
// --ids          required: the tender ids to score, separated by commas or spaces. Every other tender is ignored, so
//                the tuning half can be scored without looking at the held-out half (tools/eval_split.py prints the ids).
//
// Prints numbers only: the confusion matrix predicted kind x labelled stratum (in brackets: how many of the cell were
// predicted with high confidence), and what the flag TENDER_KIND=on would do with them. With --detail it also lists
// each tender id with its prediction, the reason and the product phrases: phrases are parts of the title, so use
// --detail on your own machine and for tuning ids only.
// --jsonl=<file> also writes one line per scored tender to a file: id, predicted kind, confidence, labelled stratum
//                and the time the classifier took (ms). No title, no phrase. Read by tools/bench_tenderkind_models.py.
import { readFileSync, writeFileSync } from "fs";
import { tenderKind } from "@/lib/tenderkind";

const KINDS = ["goods", "non_goods", "mixed", "unknown"] as const, STRATA = ["goods", "non_goods", "mixed", "no_label"] as const;
const say = (s: string) => process.stdout.write(s + "\n");
const jsonl = (p: string) => readFileSync(p, "utf-8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l) as Record<string, unknown>);

function main(argv: string[]): number {
  // the ids are every argument after --ids up to the next option: "--ids T02,T03" and "--ids T02 T03" both work
  const i0 = argv.indexOf("--ids"), rest = i0 < 0 ? [] : argv.slice(i0 + 1), stop = rest.findIndex((a) => a.startsWith("--"));
  const idArgs = stop < 0 ? rest : rest.slice(0, stop), detail = argv.includes("--detail");
  const jsonlOut = (argv.find((a) => a.startsWith("--jsonl=")) || "").slice(8), perId: string[] = [];
  const files = argv.filter((a, i) => !a.startsWith("--") && !(i0 >= 0 && i > i0 && i <= i0 + idArgs.length));
  const ids = new Set(idArgs.join(" ").split(/[\s,]+/).filter(Boolean));
  if (files.length !== 2 || !ids.size) { process.stderr.write("usage: node tk.js <tenders.jsonl> <labels.jsonl> --ids T02,T03,... [--detail]\n"); return 2; }
  const strata = new Map<string, string>();
  for (const r of jsonl(files[1])) {
    const lab = String(r.label ?? "").trim().toLowerCase().replace(/ /g, "_");
    if (Number(r.rank ?? 0) === 0 && ["goods", "non_goods", "mixed"].includes(lab)) strata.set(String(r.query_id ?? "").trim(), lab);
  }
  const cell: Record<string, { n: number; high: number }> = {};
  const at = (k: string, s: string) => (cell[`${k}|${s}`] ||= { n: 0, high: 0 });
  const lines: string[] = [], seen = new Set<string>();
  let withNature = 0, phrased = 0, goodsLike = 0;
  for (const t of jsonl(files[0])) {
    const id = String(t.query_id ?? "");
    if (!ids.has(id) || seen.has(id)) continue;
    seen.add(id);
    if (String(t.nature ?? "").trim()) withNature++;
    const t0 = performance.now();
    const r = tenderKind({ title: String(t.title ?? ""), sector: String(t.sector ?? ""), category: String(t.nature ?? "") });
    const ms = performance.now() - t0;
    const s = strata.get(id) || "no_label", c = at(r.kind, s);
    perId.push(JSON.stringify({ id, kind: r.kind, confidence: r.confidence, labelled: s, ms: Math.round(ms * 1000) / 1000 }));
    c.n++; if (r.confidence === "high") c.high++;
    if (r.kind === "goods" || r.kind === "mixed") { goodsLike++; if (r.goods_phrases.length) phrased++; }
    if (detail) lines.push(`${id}  predicted ${r.kind} (${r.confidence})  labelled ${s}  phrases ${JSON.stringify(r.goods_phrases)}  why: ${r.why}`);
  }
  const n = (k: string, s: string) => cell[`${k}|${s}`] || { n: 0, high: 0 }, pad = (x: string, w = 12) => x.padEnd(w);
  say(`tenders scored: ${seen.size} of ${ids.size} ids asked (${[...ids].filter((i) => !seen.has(i)).length} not in the tender file); with a procurement category in the row: ${withNature}`);
  say(`rows: predicted kind; columns: labelled stratum; in brackets: predicted with high confidence`);
  say(pad("") + STRATA.map((s) => pad(s)).join("") + "total");
  for (const k of KINDS) say(pad(k) + STRATA.map((s) => pad(`${n(k, s).n} (${n(k, s).high})`)).join("") + STRATA.reduce((a, s) => a + n(k, s).n, 0));
  say(pad("total") + STRATA.map((s) => pad(String(KINDS.reduce((a, k) => a + n(k, s).n, 0)))).join("") + seen.size);
  const labelled = (["goods", "non_goods", "mixed"] as const).reduce((a, s) => a + KINDS.reduce((b, k) => b + n(k, s).n, 0), 0);
  const agree = (["goods", "non_goods", "mixed"] as const).reduce((a, s) => a + n(s, s).n, 0);
  const ng = KINDS.reduce((a, k) => a + n(k, "non_goods").n, 0), buys = KINDS.reduce((a, k) => a + n(k, "goods").n + n(k, "mixed").n, 0);
  say(`same kind as the label: ${agree} of ${labelled} labelled`);
  say(`with the flag on: labelled non-goods tenders answered with an empty list ${n("non_goods", "non_goods").high} of ${ng}; ` +
    `labelled goods or mixed tenders wrongly answered with an empty list ${n("non_goods", "goods").high + n("non_goods", "mixed").high} of ${buys}`);
  say(`predicted goods or mixed: ${goodsLike}, of which a product phrase was extracted for ${phrased}`);
  if (detail) for (const l of lines.sort()) say(l);
  if (jsonlOut) writeFileSync(jsonlOut, perId.sort().map((l) => l + "\n").join("") + JSON.stringify({ id: "_process", rss_bytes: process.memoryUsage().rss }) + "\n");
  return 0;
}
process.exit(main(process.argv.slice(2)));
