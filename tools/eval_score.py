"""Scores the blind supplier-match evaluation (dealdesk/tools/eval-suppliers.ts --blind, workflow supplier-eval).

  python3 tools/eval_score.py rows.jsonl verdicts.jsonl labels.jsonl [--tenders tenders.jsonl] [--summary summary.json]
                              [--human human_labels.jsonl] [--json]

rows.jsonl      what the search returned (no verdict in it): set, query_id, query, rank, supplier, ...
verdicts.jsonl  the matcher's own bucket and reason, keyed by (set, query_id, rank)
labels          the independent labeller's file, JSON lines or CSV: query_id, rank, label, reason
                label is one of relevant / partly / irrelevant / cannot_tell
                (a line with rank 0 and label goods / non_goods / mixed overrules the stratum of a tender)
tenders.jsonl   the tender set: stratum and what the search derived from each title
summary.json    the requests that were run, so a request that returned nothing still counts as a miss

Reported separately for the product set (ids Q..) and the tender set (ids T..):
  precision at 5, 10 and 25, pooled over all labelled rows and averaged over requests, and per request;
  precision per matcher bucket (what share of "supported" is really relevant, and of "plausible");
  the share of requests with no relevant result in the top 10; the 30 worst false positives with the matcher's reason.
For the tender set also: the share of non-goods tenders for which any supplier was returned at all (each such row is
a false positive whatever its label says).

Counting rules. Precision = relevant / (relevant + partly + irrelevant); "partly" is the right product with the
wrong specification and does not count as a hit (a second figure counts it). cannot_tell and unlabelled rows are
left out of the denominator and their number is shown, so a figure never hides how small its sample is.

The output names suppliers: run it on your own machine, never in a workflow (the repository's logs are public).
"""
import argparse
import csv
import json
import sys
from collections import defaultdict

LABELS = ("relevant", "partly", "irrelevant", "cannot_tell")
STRATA = ("goods", "non_goods", "mixed")
BUCKET_ORDER = {"supported": 0, "plausible": 1, "related": 2}
KS = (5, 10, 25)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_labels(path):
    """JSON lines or CSV (header: query_id, rank, label, reason). Returns (row labels, tender stratum overrides)."""
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    first = text.lstrip()[:1]
    recs = [json.loads(line) for line in text.splitlines() if line.strip()] if first == "{" else list(csv.DictReader(text.splitlines()))
    labels, strata, bad = {}, {}, []
    for r in recs:
        qid = str(r.get("query_id") or "").strip()
        lab = str(r.get("label") or "").strip().lower().replace(" ", "_")
        try:
            rank = int(str(r.get("rank") or "0").strip() or 0)
        except ValueError:
            bad.append(r)
            continue
        if not qid or not lab:
            continue
        if rank == 0 and lab in STRATA:
            strata[qid] = lab
        elif rank > 0 and lab in LABELS:
            labels[(qid, rank)] = (lab, str(r.get("reason") or "").strip())
        else:
            bad.append(r)
    return labels, strata, bad


def set_of(qid, rec=None):
    return (rec or {}).get("set") or ("tender" if str(qid).startswith("T") else "product")


def _prec(labs):
    """labs: list of labels (None = unlabelled). Returns the counts and the two precision figures."""
    n = {k: sum(1 for x in labs if x == k) for k in LABELS}
    judged = n["relevant"] + n["partly"] + n["irrelevant"]
    return {"relevant": n["relevant"], "partly": n["partly"], "irrelevant": n["irrelevant"], "cannot_tell": n["cannot_tell"],
            "unlabelled": sum(1 for x in labs if x is None), "judged": judged,
            "precision": n["relevant"] / judged if judged else None,
            "precision_with_partly": (n["relevant"] + n["partly"]) / judged if judged else None}


def score_set(name, rows, verdicts, labels, queries, strata=None):
    """rows / verdicts of one set; queries: {query_id: text} for every request run (also those with no rows)."""
    by_q = defaultdict(list)
    for r in rows:
        by_q[r["query_id"]].append(r)
    for qid in by_q:
        by_q[qid].sort(key=lambda r: r["rank"])
    qids = sorted(set(queries) | set(by_q))
    lab = lambda r: (labels.get((r["query_id"], r["rank"])) or (None, ""))[0]
    per_query, pooled, macro = [], {}, {}
    for qid in qids:
        top = by_q.get(qid, [])
        e = {"query_id": qid, "query": queries.get(qid) or (top[0]["query"] if top else ""), "returned": len(top)}
        if strata is not None:
            e["stratum"] = strata.get(qid, "")
        for k in KS:
            e[f"p@{k}"] = _prec([lab(r) for r in top[:k]])
        e["relevant_in_top10"] = e["p@10"]["relevant"]
        # a request counts as a miss when nothing came back, or when its whole top 10 was labelled and none is relevant
        e["top10_fully_labelled"] = all(lab(r) is not None for r in top[:10])
        per_query.append(e)
    for k in KS:
        pooled[k] = _prec([lab(r) for qid in qids for r in by_q.get(qid, [])[:k]])
        vals = [e[f"p@{k}"]["precision"] for e in per_query if e[f"p@{k}"]["precision"] is not None]
        macro[k] = sum(vals) / len(vals) if vals else None
    decided = [e for e in per_query if e["returned"] == 0 or (e["top10_fully_labelled"] and e["p@10"]["judged"] > 0)]
    zero = [e for e in decided if e["relevant_in_top10"] == 0]
    buckets = {}
    for b in sorted({v.get("bucket") or "none" for v in verdicts.values()}, key=lambda x: (BUCKET_ORDER.get(x, 9), x)):
        buckets[b] = _prec([lab(r) for r in rows if (verdicts.get((r["query_id"], r["rank"])) or {}).get("bucket", "none") == b])
    fps = []
    for r in rows:
        l, why = labels.get((r["query_id"], r["rank"])) or (None, "")
        if l != "irrelevant":
            continue
        v = verdicts.get((r["query_id"], r["rank"])) or {}
        fps.append({"query_id": r["query_id"], "query": r["query"], "rank": r["rank"], "supplier": r.get("supplier", ""), "country": r.get("country", ""),
                    "bucket": v.get("bucket", ""), "matcher_reason": v.get("reason", ""), "evidence_basis": v.get("evidence_basis", ""), "labeller_reason": why})
    # worst first: the more confident the matcher was and the higher it ranked the row, the worse the miss
    fps.sort(key=lambda x: (BUCKET_ORDER.get(x["bucket"], 9), x["rank"], x["query_id"]))
    out = {"set": name, "requests": len(qids), "rows": len(rows), "labelled_rows": sum(1 for r in rows if lab(r) is not None),
           "pooled": pooled, "macro": macro, "per_bucket": buckets,
           "requests_decided_for_top10": len(decided), "requests_with_no_relevant_in_top10": len(zero),
           "share_no_relevant_in_top10": len(zero) / len(decided) if decided else None,
           "requests_with_no_rows": sum(1 for e in per_query if e["returned"] == 0),
           "worst_false_positives": fps[:30], "false_positives_total": len(fps), "per_query": per_query}
    if strata is not None:
        ng = [e for e in per_query if e.get("stratum") == "non_goods"]
        hit = [e for e in ng if e["returned"] > 0]
        out["non_goods_tenders"] = len(ng)
        out["non_goods_tenders_with_any_supplier"] = len(hit)
        out["share_non_goods_with_any_supplier"] = len(hit) / len(ng) if ng else None
        out["non_goods_rows_returned"] = sum(e["returned"] for e in ng)
        out["per_stratum"] = {s: {k: _prec([lab(r) for e in per_query if e.get("stratum") == s for r in by_q.get(e["query_id"], [])[:k]]) for k in KS} for s in STRATA}
    return out


def score_human(rows, verdicts, human):
    """The owner's own verdicts against this run: pairs (asked text or product, supplier) that the run returned."""
    norm = lambda s: " ".join(str(s or "").lower().split())
    idx = defaultdict(list)
    for r in rows:
        idx[(norm(r["query"]), norm(r.get("supplier")))].append(r)
    out = {"owner_verdicts": len(human), "by_label": {}, "matched_rows": 0, "owner_no_still_returned": []}
    for h in human:
        out["by_label"][h.get("label", "")] = out["by_label"].get(h.get("label", ""), 0) + 1
        hits = idx.get((norm(h.get("asked")), norm(h.get("supplier"))), []) + (idx.get((norm(h.get("product")), norm(h.get("supplier"))), []) if norm(h.get("product")) != norm(h.get("asked")) else [])
        for r in hits:
            out["matched_rows"] += 1
            if h.get("label") == "no":
                v = verdicts.get((r["query_id"], r["rank"])) or {}
                out["owner_no_still_returned"].append({"query_id": r["query_id"], "rank": r["rank"], "supplier": r.get("supplier", ""), "bucket": v.get("bucket", ""), "matcher_reason": v.get("reason", "")})
    return out


def score(rows, verdicts, labels, tenders=None, summary=None, strata_override=None, human=None):
    vmap = {(v["query_id"], v["rank"]): v for v in verdicts}
    out = {}
    tmeta = {t["query_id"]: t for t in (tenders or [])}
    for name in ("product", "tender"):
        mine = [r for r in rows if set_of(r["query_id"], r) == name]
        queries = {r["query_id"]: r["query"] for r in mine}
        for e in ((summary or {}).get(name) or {}).get("per_query") or []:
            queries.setdefault(e["id"], "")
        strata = None
        if name == "tender":
            for qid, t in tmeta.items():
                queries[qid] = queries.get(qid) or t.get("title", "")
            strata = {qid: t.get("stratum", "") for qid, t in tmeta.items()}
            strata.update(strata_override or {})
        if not queries and name == "tender":
            continue
        out[name] = score_set(name, mine, {k: v for k, v in vmap.items() if set_of(k[0], v) == name}, labels, queries, strata)
    if human is not None:
        out["owner_ground_truth"] = score_human(rows, vmap, human)
    return out


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _line(p):
    extra = f", {p['cannot_tell']} cannot tell" if p["cannot_tell"] else ""
    extra += f", {p['unlabelled']} not labelled" if p["unlabelled"] else ""
    return f"{_pct(p['precision'])} relevant ({p['relevant']} of {p['judged']} judged; with 'partly' {_pct(p['precision_with_partly'])}{extra})"


def render(res):
    L = []
    for name in ("product", "tender"):
        s = res.get(name)
        if not s:
            continue
        L += ["", f"=== {name.upper()} SET: {s['requests']} requests, {s['rows']} rows returned, {s['labelled_rows']} labelled ==="]
        for k in KS:
            L.append(f"precision at {k:<2} pooled: {_line(s['pooled'][k])}; mean over requests: {_pct(s['macro'][k])}")
        L.append("precision per matcher bucket:")
        for b, p in s["per_bucket"].items():
            L.append(f"  {b:<10} {_line(p)}")
        L.append(f"requests with no relevant result in the top 10: {s['requests_with_no_relevant_in_top10']} of {s['requests_decided_for_top10']} ({_pct(s['share_no_relevant_in_top10'])}); "
                 f"{s['requests_with_no_rows']} returned nothing; {s['requests'] - s['requests_decided_for_top10']} not fully labelled yet")
        if "non_goods_tenders" in s:
            L.append(f"non-goods tenders (works, services, consulting, programmes) for which any supplier was returned: {s['non_goods_tenders_with_any_supplier']} of {s['non_goods_tenders']} "
                     f"({_pct(s['share_non_goods_with_any_supplier'])}); {s['non_goods_rows_returned']} supplier rows that should not exist")
            for st in STRATA:
                L.append(f"  {st:<9} precision at 10: {_line(s['per_stratum'][st][10])}")
        L.append("per request (returned | p@5 | p@10 | p@25):")
        for e in s["per_query"]:
            L.append(f"  {e['query_id']} {e.get('stratum', ''):<9} {e['returned']:>2} | {_pct(e['p@5']['precision']):>4} | {_pct(e['p@10']['precision']):>4} | {_pct(e['p@25']['precision']):>4} | {e['query'][:70]}")
        L.append(f"worst false positives ({len(s['worst_false_positives'])} of {s['false_positives_total']}):")
        for x in s["worst_false_positives"]:
            L.append(f"  {x['query_id']} #{x['rank']:<2} [{x['bucket'] or '-'}] {x['supplier']} ({x['country']}) for \"{x['query'][:50]}\"")
            L.append(f"      matcher: {x['matcher_reason'] or '-'} | labeller: {x['labeller_reason'] or '-'}")
    h = res.get("owner_ground_truth")
    if h:
        L += ["", f"=== OWNER'S OWN VERDICTS: {h['owner_verdicts']} ({', '.join(f'{k} {v}' for k, v in sorted(h['by_label'].items()))}) ===",
              f"pairs of this run that the owner has judged: {h['matched_rows']}; judged 'no' and still returned: {len(h['owner_no_still_returned'])}"]
        for x in h["owner_no_still_returned"][:30]:
            L.append(f"  {x['query_id']} #{x['rank']} [{x['bucket']}] {x['supplier']} | matcher: {x['matcher_reason']}")
    return "\n".join(L).lstrip("\n") + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score the blind supplier-match evaluation.")
    ap.add_argument("rows"), ap.add_argument("verdicts"), ap.add_argument("labels")
    ap.add_argument("--tenders"), ap.add_argument("--summary"), ap.add_argument("--human")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    a = ap.parse_args(argv)
    labels, strata, bad = read_labels(a.labels)
    res = score(read_jsonl(a.rows), read_jsonl(a.verdicts), labels, read_jsonl(a.tenders) if a.tenders else None,
                json.load(open(a.summary, encoding="utf-8")) if a.summary else None, strata, read_jsonl(a.human) if a.human else None)
    if bad:
        print(f"WARNING: {len(bad)} label lines were not understood (label must be one of {', '.join(LABELS)})", file=sys.stderr)
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
