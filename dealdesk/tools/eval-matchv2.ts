// Measures supplier matching v2 (lib/matchv2.ts) against the blind labels, on rows the search already returned.
//
//   cd dealdesk && npx --yes esbuild@0.24.0 tools/eval-matchv2.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=/tmp/m2.js --log-level=error
//   node /tmp/m2.js --data <dir> --phase tune|final [--tiebreak on|off] [--run-cap N] [--task-cap 60]
//
// <dir> holds what deploy/ops/_matchv2_root.sh cut out on the server for ONE half of the frozen split: rows.jsonl,
// labels.jsonl, tenders.jsonl, verdicts.jsonl (only the matcher's "kind" is read: maker / trader), ids.txt, and the
// Gemini state (gemini_state.json: every answer ever paid for, and the call count of this task) plus, for the tuning
// half, f10_seed.json (benchmark F10's tender-kind answers to the same question, so they are not bought twice).
//
// Variants, all on the same rows and the same labels: base (the order the search returned), A (tender kind routing),
// B (fit re-rank, code only), A+B, and A+B with the Gemini tie-break. Nothing is retrieved again, so every row of a new
// top 10 was in the labelled set; the tool counts and prints any that is not.
//
// Metric (the supervisor's B metric): per request, relevant in the top 10 (an empty list is 0 of 10); partly counted
// apart; per stratum: product requests, goods tenders, non_goods tenders (is the list correctly empty), mixed tenders.
// THE LOG IS PUBLIC: ids, counts and metrics only. Per-request ranks go to detail_<phase>.jsonl, which the root step
// keeps on the server and copies to Google Drive. For the final (held-out) phase only totals are printed.
import { existsSync, readFileSync, writeFileSync } from "fs";
import path from "path";
import { tenderKind, type TenderKind } from "@/lib/tenderkind";
import { applyTie, askGeminiForKind, ownFromEvidence, fitRerank, requestRequirement, routeTender, tieToBreak, type FitRow, type Kind3, type Ranked } from "@/lib/matchv2";
import { decide, fitInput, kindInput, kindQuestions } from "@/lib/gemini";

const say = (s = "") => process.stdout.write(s + "\n");
const jsonl = (p: string) => (existsSync(p) ? readFileSync(p, "utf-8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l) as Record<string, unknown>) : []);
const arg = (k: string, d = "") => { const i = process.argv.indexOf(k); return i >= 0 ? String(process.argv[i + 1] || d) : d; };
const TUNE = "Q05 Q06 Q07 Q08 Q09 Q13 Q14 Q15 Q19 Q20 Q24 Q25 Q26 Q27 Q30 Q31 Q33 Q34 Q35 Q37 Q39 Q40 T02 T03 T05 T07 T09 T10 T11 T12 T13 T14 T18 T19 T21 T23 T24 T27".split(" ");

type Row = { qid: string; rank: number; query: string; evidence: string; type: string; kind: string; label: string | null };
type State = { calls: number; calls_by_phase: Record<string, number>; kind: Record<string, { answer: Kind3; from: string }>; fit: Record<string, Record<string, "yes" | "no">>;
  events: { at: string; phase: string; what: string; id: string; ok: boolean; reason?: string }[]; stopped?: string };


async function main(): Promise<number> {
  const dir = arg("--data"), phase = arg("--phase"), tiebreak = arg("--tiebreak", "on") === "on";
  const runCap = Number(arg("--run-cap", "0")), taskCap = Number(arg("--task-cap", "60"));
  if (!dir || !["tune", "final"].includes(phase)) { say("usage: --data <dir> --phase tune|final"); return 2; }
  const ids = readFileSync(path.join(dir, "ids.txt"), "utf-8").split(/[\s,]+/).filter(Boolean).sort();
  // the halves must not mix: the tuning phase sees only tuning ids, the final phase none of them
  if (phase === "tune" ? ids.some((i) => !TUNE.includes(i)) : ids.some((i) => TUNE.includes(i))) { say("the id list does not belong to this phase: stopped"); return 2; }
  const idSet = new Set(ids);
  const labels = new Map<string, string>(), strata = new Map<string, string>();
  for (const r of jsonl(path.join(dir, "labels.jsonl"))) {
    const q = String(r.query_id || "").trim(), rank = Number(r.rank || 0), lab = String(r.label || "").trim().toLowerCase().replace(/ /g, "_");
    if (!idSet.has(q)) continue;
    if (rank === 0) { if (["goods", "non_goods", "mixed"].includes(lab)) strata.set(q, lab); } else labels.set(`${q}#${rank}`, lab);
  }
  const kinds = new Map<string, string>();
  for (const v of jsonl(path.join(dir, "verdicts.jsonl"))) kinds.set(`${v.query_id}#${v.rank}`, String(v.kind || ""));
  const tenders = new Map<string, Record<string, unknown>>();
  for (const t of jsonl(path.join(dir, "tenders.jsonl"))) if (idSet.has(String(t.query_id))) tenders.set(String(t.query_id), t);
  const byQ = new Map<string, Row[]>();
  for (const r of jsonl(path.join(dir, "rows.jsonl"))) {
    const qid = String(r.query_id || "");
    if (!idSet.has(qid)) continue;
    const rank = Number(r.rank), key = `${qid}#${rank}`;
    (byQ.get(qid) || byQ.set(qid, []).get(qid)!).push({ qid, rank, query: String(r.query || ""), evidence: String(r.evidence || ""), type: String(r.type || ""), kind: kinds.get(key) || "", label: labels.get(key) ?? null });
  }
  for (const rs of byQ.values()) rs.sort((a, b) => a.rank - b.rank);

  // ---- Gemini state: every answer is kept by request id (and row rank), so a rerun never asks again
  const sp = path.join(dir, "gemini_state.json");
  const st: State = existsSync(sp) ? JSON.parse(readFileSync(sp, "utf-8")) : { calls: 0, calls_by_phase: {}, kind: {}, fit: {}, events: [] };
  st.calls_by_phase ||= {}; st.kind ||= {}; st.fit ||= {}; st.events ||= []; delete st.stopped;
  const seedP = path.join(dir, "f10_seed.json"), seed: Record<string, Kind3> = phase === "tune" && existsSync(seedP) ? JSON.parse(readFileSync(seedP, "utf-8")) : {};
  const key = String(process.env.GEMINI_API_KEY || "").trim();
  let runCalls = 0;
  const save = () => writeFileSync(sp, JSON.stringify(st));
  const stoppedWhy = (): string => (st as { stopped?: string }).stopped || "";
  const canCall = () => !!key && !stoppedWhy() && runCalls < runCap && st.calls < taskCap;
  // the free tier refused a fast burst (tuning run 43192935918: HTTP 429 at call 20), so calls are paced; a 429 gets
  // one more attempt after a minute, and every attempt counts against the caps
  const PACE_MS = Number(process.env.MATCHV2_PACE_MS || 6000), sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  let lastCall = 0;
  const ask = async (what: string, id: string, input: string, qs: Parameters<typeof decide>[1]): Promise<Awaited<ReturnType<typeof decide>>> => {
    for (let attempt = 0; ; attempt++) {
      const wait = lastCall + PACE_MS - Date.now();
      if (wait > 0) await sleep(wait);
      st.calls++; runCalls++; st.calls_by_phase[phase] = (st.calls_by_phase[phase] || 0) + 1; save();   // counted before it is sent
      lastCall = Date.now();
      const r = await decide(input, qs, key);
      st.events.push({ at: new Date().toISOString(), phase, what, id, ok: r.ok, ...(r.ok ? {} : { reason: r.reason }) });
      if (!r.ok && r.status === 429 && attempt === 0 && runCalls < runCap && st.calls < taskCap) { save(); await sleep(65000); continue; }
      if (!r.ok) st.stopped = `${what} ${id}: ${r.reason}`;
      save();
      return r;
    }
  };

  // ---- A. tender kind: rules, then Gemini where the rules are not a strong goods reading
  const rulesOf = new Map<string, TenderKind>(), gemOf = new Map<string, Kind3 | null>();
  for (const id of ids.filter((i) => i.startsWith("T"))) {
    const t = tenders.get(id) || {};
    const k = tenderKind({ title: String(t.title || ""), sector: String(t.sector || ""), category: String(t.nature || "") });
    rulesOf.set(id, k);
    if (!askGeminiForKind(k)) { gemOf.set(id, null); continue; }
    if (!st.kind[id] && seed[id]) st.kind[id] = { answer: seed[id], from: "benchmark F10 (run 43176919653), same question" };
    if (!st.kind[id] && canCall()) {
      const r = await ask("kind", id, kindInput({ title: String(t.title || ""), sector: String(t.sector || ""), category: String(t.nature || "") }), kindQuestions());
      if (r.ok && r.answers.kind) st.kind[id] = { answer: r.answers.kind.choice as Kind3, from: "this task" };
    }
    gemOf.set(id, st.kind[id]?.answer ?? null);
  }
  save();

  // ---- B. conditions and the re-rank, per request
  type Out = { id: string; stratum: string; variants: Record<string, Row[]>; dropped: Row[]; tieAsked: number; tieCached: boolean; conds: string[]; route?: ReturnType<typeof routeTender> };
  const outs: Out[] = [];
  let tieNeeded = 0, tieSkipped = 0;
  for (const id of ids) {
    const rows = byQ.get(id) || [], isT = id.startsWith("T"), t = tenders.get(id) || {};
    const stratum = isT ? strata.get(id) || "no_label" : "product";
    const k = rulesOf.get(id);
    const route = isT && k ? routeTender(k, gemOf.get(id) ?? null) : undefined;
    const req = requestRequirement(rows[0]?.query || "", isT && k ? { kind: k, title: String(t.title || ""), commodity: String(t.commodity || "") } : undefined);
    const toRow = (r: Row): FitRow => ({ own: ownFromEvidence(r.evidence), kind: r.kind });
    const { kept, dropped } = fitRerank(rows, req.conds, toRow);
    const B = kept.map((x) => x.item);
    // the tie-break: one call for the rows of a wide tie that straddles rank 10
    let ABg: Row[] = B, tieAsked = 0, tieCached = false;
    const pos = tieToBreak(kept);
    if (pos.length && !(route?.block)) {
      tieNeeded++;
      const cache = st.fit[id] || {};
      const missing = pos.filter((i) => !cache[String(kept[i].item.rank)]);
      const product = req.product;
      if (missing.length && tiebreak && canCall()) {
        const { input, questions } = fitInput(product, missing.map((i) => ({ text: `${kept[i].item.evidence} | type: ${kept[i].item.type || "-"}` })));
        const r = await ask("tie", id, input, questions);
        if (r.ok) { missing.forEach((i, n) => { const a = r.answers[`r${n + 1}`]; if (a && (a.choice === "yes" || a.choice === "no")) cache[String(kept[i].item.rank)] = a.choice; }); st.fit[id] = cache; save(); tieAsked = missing.length; }
      } else if (missing.length) tieSkipped++;
      else tieCached = true;
      const ans = new Map<number, "yes" | "no">();
      for (const i of pos) { const a = cache[String(kept[i].item.rank)]; if (a) ans.set(i, a); }
      if (ans.size) ABg = applyTie(kept as Ranked<Row>[], ans).map((x) => x.item);
    }
    const blocked = !!route?.block;
    outs.push({ id, stratum, dropped: dropped.map((x) => x.item), tieAsked, tieCached, route,
      conds: isT ? req.conds.map((c) => c.kind) : req.conds.map((c) => (c.kind === "product" ? `product:${c.label}` : `${c.kind}:${c.label}`)),
      variants: { base: rows, A: blocked ? [] : rows, B, AB: blocked ? [] : B, ABg: blocked ? [] : ABg } });
  }

  // ---- metrics
  const VARIANTS = [["base", "baseline (as returned)"], ["A", "A tender kind"], ["B", "B fit re-rank, code"], ["AB", "A+B code"], ["ABg", "A+B + Gemini tie-break"]] as const;
  const top = (rs: Row[]) => rs.slice(0, 10);
  const m = (rs: Row[]) => { const t10 = top(rs), c = (l: string) => t10.filter((r) => r.label === l).length;
    return { rel: c("relevant"), partly: c("partly"), irr: c("irrelevant"), ct: c("cannot_tell"), unl: t10.filter((r) => r.label === null).length, n: rs.length }; };
  const STRATA = [["product", "product requests"], ["goods", "goods tenders"], ["non_goods", "non_goods tenders"], ["mixed", "mixed tenders"], ["no_label", "tenders without a stratum label"]] as const;
  const summary: Record<string, unknown> = { phase, ids: ids.length, variants: {} };
  say(`SUPPLIER MATCHING V2 - ${phase === "tune" ? "TUNING half" : "HELD-OUT half (final check, run once)"}: ${ids.length} requests (${ids.filter((i) => i.startsWith("Q")).length} product, ${ids.filter((i) => i.startsWith("T")).length} tender); rows ${[...byQ.values()].reduce((a, r) => a + r.length, 0)}; labelled rows ${[...labels.keys()].length}`);
  say("metric: relevant in the top 10 per request (empty list = 0 of 10), summed per stratum; partly apart; mean = sum / requests");
  say("");
  say("| stratum | requests | variant | relevant in top 10 (sum) | mean of 10 | partly (sum) | requests returning nothing | requests with 0 relevant | non_goods correctly empty | cannot_tell / unlabelled in top 10 |");
  say("|---|---|---|---|---|---|---|---|---|---|");
  for (const [s, name] of STRATA) {
    const os = outs.filter((o) => o.stratum === s);
    if (!os.length) continue;
    for (const [v, vname] of VARIANTS) {
      const ms = os.map((o) => m(o.variants[v]));
      const sum = (f: (x: ReturnType<typeof m>) => number) => ms.reduce((a, x) => a + f(x), 0);
      const empty = ms.filter((x) => x.n === 0).length, zero = ms.filter((x) => x.rel === 0).length;
      const ngOk = s === "non_goods" ? `${empty} of ${os.length}` : "-";
      say(`| ${name} | ${os.length} | ${vname} | ${sum((x) => x.rel)} of ${10 * os.length} | ${(sum((x) => x.rel) / os.length).toFixed(2)} | ${sum((x) => x.partly)} | ${empty} | ${zero} | ${ngOk} | ${sum((x) => x.ct)} / ${sum((x) => x.unl)} |`);
      (summary.variants as Record<string, unknown>)[`${s}|${v}`] = { requests: os.length, relevant: sum((x) => x.rel), partly: sum((x) => x.partly), empty, zero_relevant: zero, cannot_tell: sum((x) => x.ct), unlabelled: sum((x) => x.unl), zero_ids: os.filter((o, i) => ms[i].rel === 0).map((o) => o.id) };
    }
  }
  // the decision inputs: goods requests (product requests and goods tenders) that end at zero, and those the change made zero
  const goodsLike = outs.filter((o) => o.stratum === "product" || o.stratum === "goods");
  say("");
  for (const v of ["AB", "ABg"]) {
    const atZero = goodsLike.filter((o) => m(o.variants[v]).rel === 0).map((o) => o.id), madeZero = goodsLike.filter((o) => m(o.variants.base).rel > 0 && m(o.variants[v]).rel === 0).map((o) => o.id);
    const worse = goodsLike.filter((o) => m(o.variants[v]).rel < m(o.variants.base).rel).map((o) => o.id), better = goodsLike.filter((o) => m(o.variants[v]).rel > m(o.variants.base).rel).map((o) => o.id);
    const mixedEmptied = outs.filter((o) => (o.stratum === "mixed" || o.stratum === "goods") && o.route?.block).map((o) => o.id);
    say(`${v}: goods requests (product + goods tenders) at 0 relevant: ${atZero.length}${atZero.length ? " (" + atZero.join(" ") + ")" : ""}; made 0 by the change: ${madeZero.length}${madeZero.length ? " (" + madeZero.join(" ") + ")" : ""}; ` +
      `better than base: ${better.length}, worse: ${worse.length}${phase === "tune" && worse.length ? " (" + worse.join(" ") + ")" : ""}; goods or mixed tenders emptied by A: ${mixedEmptied.length}${mixedEmptied.length ? " (" + mixedEmptied.join(" ") + ")" : ""}`);
    (summary as Record<string, unknown>)[`decision_${v}`] = { at_zero: atZero, made_zero: madeZero, better: better.length, worse: worse.length, goods_or_mixed_emptied: mixedEmptied };
  }
  const unl = outs.reduce((a, o) => a + m(o.variants.ABg).unl + m(o.variants.AB).unl + m(o.variants.B).unl, 0);
  say(`rows in a new top 10 without a label: ${unl} (the re-rank only moves and drops rows of the labelled set, so this must be 0)`);
  const dr = outs.flatMap((o) => o.dropped), dc = (l: string | null) => dr.filter((r) => r.label === l).length;
  say(`rows dropped as contradicting a stated condition: ${dr.length} (labelled relevant ${dc("relevant")}, partly ${dc("partly")}, irrelevant ${dc("irrelevant")}, cannot_tell ${dc("cannot_tell")}, no label ${dc(null)})`);
  const T = outs.filter((o) => o.route);
  say(`tender kind: rules alone trusted for ${T.filter((o) => o.route!.gemini === null && !askGeminiForKind(rulesOf.get(o.id)!)).length}, Gemini consulted for ${T.filter((o) => askGeminiForKind(rulesOf.get(o.id)!)).length} ` +
    `(answer available for ${T.filter((o) => o.route!.gemini !== null).length}); lists emptied: ${T.filter((o) => o.route!.block).length}`);
  say(`Gemini tie-break: requests with a wide tie across rank 10: ${tieNeeded}; asked now ${outs.filter((o) => o.tieAsked).length} (rows ${outs.reduce((a, o) => a + o.tieAsked, 0)}), from the cache ${outs.filter((o) => o.tieCached).length}, skipped (budget, no key or stopped) ${tieSkipped}${tiebreak ? "" : " - tie-break switched off for this run"}`);
  say(`Google calls: this run ${runCalls}; this task so far ${st.calls} of ${taskCap} (tune ${st.calls_by_phase.tune || 0}, final ${st.calls_by_phase.final || 0}); key present: ${key ? "yes" : "NO"}${stoppedWhy() ? "; STOPPED: " + stoppedWhy().replace(/[^A-Za-z0-9 _:#.\-]/g, "") : ""}`);
  if (phase === "tune") {
    say("");
    say("per request (tuning ids only): base rel/partly/rows -> A+B code -> A+B+tie; dropped rows; tender: rules kind (confidence) / Gemini kind / emptied");
    for (const o of outs) {
      const f = (v: string) => { const x = m(o.variants[v]); return `${x.rel}/${x.partly}/${x.n}`; };
      const r = o.route ? ` | rules ${o.route.rules} (${rulesOf.get(o.id)!.confidence}) / gemini ${o.route.gemini ?? "-"} / ${o.route.block ? "EMPTIED" : "kept"}` : "";
      const d = o.dropped.length ? ` | dropped ${o.dropped.length} (rel ${o.dropped.filter((x) => x.label === "relevant").length})` : "";
      say(`  ${o.id} ${o.stratum.padEnd(9)} ${f("base").padEnd(9)} -> ${f("AB").padEnd(9)} -> ${f("ABg").padEnd(9)}${d}${o.tieAsked ? ` | tie asked ${o.tieAsked}` : o.tieCached ? " | tie cached" : ""}${r} | conditions: ${o.conds.join(", ") || "none"}`);
    }
  }
  // detail for the server and Drive: ranks only, no names and no text
  writeFileSync(path.join(dir, `detail_${phase}.jsonl`), outs.map((o) => JSON.stringify({ id: o.id, stratum: o.stratum, conds: o.conds,
    route: o.route ? { rules: o.route.rules, rules_confidence: rulesOf.get(o.id)!.confidence, gemini: o.route.gemini, block: o.route.block } : null,
    ranks: Object.fromEntries(Object.entries(o.variants).map(([v, rs]) => [v, rs.map((r) => r.rank)])), dropped: o.dropped.map((r) => r.rank),
    labels_top10: Object.fromEntries(Object.entries(o.variants).map(([v, rs]) => [v, m(rs)])), tie_asked: o.tieAsked })).join("\n") + "\n");
  summary.google = { run: runCalls, task: st.calls, by_phase: st.calls_by_phase, stopped: stoppedWhy() || null };
  writeFileSync(path.join(dir, `summary_${phase}.json`), JSON.stringify(summary, null, 1));
  if (phase === "final") writeFileSync(path.join(dir, "final_reported"), new Date().toISOString() + "\n");
  return 0;
}

main().then((c) => process.exit(c), (e) => {
  // the log is public: the kind of fault and where, never its text
  const where = String((e as Error)?.stack || "").split("\n").slice(1, 3).map((l) => (l.match(/:(\d+):\d+\)?$/) || [])[1]).filter(Boolean).join(",");
  say(`eval-matchv2 failed: ${(e as Error)?.name || "error"} at ${where}`);
  process.exit(1);
});
