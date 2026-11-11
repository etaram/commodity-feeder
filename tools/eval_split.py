"""Freezes the tuning / held-out split of the supplier-match evaluation and reports the baseline of each half.

  python3 tools/eval_split.py score.json labels.jsonl dealdesk/lib/evalqueries.ts split_manifest.json

The split is by request, never by row. Product requests of one product family (the third field of E(...) in
evalqueries.ts) always land on the same side, so a fix tuned on "grains" is not tested on "grains". Tender requests
are split inside each stratum (goods / non_goods / mixed, as the blind labeller decided). The assignment is a seeded
shuffle; the manifest is written once and never overwritten: a second run reads it and only reports.
Prints numbers and request ids only (ids are public in the repository); never a company name. Per-request figures are
printed for the tuning half only: the held-out half is shown as totals, so nobody tunes on it by eye.
"""
import hashlib
import json
import os
import random
import re
import sys

SEED = "sinder-eval-split-2026-11-12"


def families(ts_path):
    src = open(ts_path, encoding="utf-8").read()
    return dict(re.findall(r'E\("(Q\d+)",\s*"(?:[^"\\]|\\.)*",\s*"([^"]+)"', src))


def make_split(per_product, per_tender, fam):
    rng, side = random.Random(SEED), {}
    groups = {}
    for e in per_product:
        groups.setdefault(fam.get(e["query_id"]) or "?" + e["query_id"], []).append(e["query_id"])
    names = sorted(groups); rng.shuffle(names)
    for i, g in enumerate(names):
        for q in groups[g]:
            side[q] = "tune" if i % 2 == 0 else "heldout"
    for stratum in sorted({e.get("stratum") or "" for e in per_tender}):
        ids = sorted(e["query_id"] for e in per_tender if (e.get("stratum") or "") == stratum); rng.shuffle(ids)
        for i, q in enumerate(ids):
            side[q] = "tune" if i % 2 == 0 else "heldout"
    return side


def report(name, es, detail):
    goods = [e for e in es if e.get("stratum") != "non_goods"]
    scored = [e for e in goods if e["returned"] and e["p@10"]["judged"]]
    ps = [e["p@10"]["precision"] for e in scored]
    zero = [e for e in goods if e["returned"] == 0 or (e["p@10"]["judged"] and e["p@10"]["relevant"] == 0)]
    hit7 = sum(1 for e in scored if e["p@10"]["relevant"] >= 7)
    line = (f"  {name}: requests {len(goods)}, scored {len(scored)}, mean P@10 {100 * sum(ps) / len(ps):.1f}% " if ps else f"  {name}: requests {len(goods)}, scored 0, ")
    print(line + f"min P@10 {100 * min(ps):.0f}%, " * bool(ps) + f"requests with 7+ relevant in top 10: {hit7}, with none (or nothing returned): {len(zero)}, "
          f"cannot_tell in top 10: {sum(e['p@10']['cannot_tell'] for e in goods)}, unlabelled in top 10: {sum(e['p@10']['unlabelled'] for e in goods)}")
    ng = [e for e in es if e.get("stratum") == "non_goods"]
    if ng:
        print(f"  {name} non-goods tenders: {len(ng)}, of which suppliers were returned for {sum(1 for e in ng if e['returned'])} (correct answer: none)")
    if detail:
        print("    per request (relevant/judged in top 10): " + ", ".join(f"{e['query_id']} {e['p@10']['relevant']}/{e['p@10']['judged']}" for e in sorted(goods, key=lambda e: e["query_id"])))


def main(a):
    score_p, labels_p, ts_p, man_p = a
    res = json.load(open(score_p, encoding="utf-8"))
    prod, tend = res["product"]["per_query"], res["tender"]["per_query"]
    labels_sha = hashlib.sha256(open(labels_p, "rb").read()).hexdigest()
    if os.path.exists(man_p):
        man = json.load(open(man_p, encoding="utf-8")); print("split manifest: existing one read, not changed")
    else:
        side = make_split(prod, tend, families(ts_p))
        man = {"seed": SEED, "rule": "product requests by product family, tender requests inside each labelled stratum; seeded shuffle, alternate sides",
               "labels_sha256": labels_sha, "tune": sorted(q for q, s in side.items() if s == "tune"), "heldout": sorted(q for q, s in side.items() if s == "heldout")}
        man["split_sha256"] = hashlib.sha256(json.dumps([man["tune"], man["heldout"]]).encode()).hexdigest()
        json.dump(man, open(man_p, "w", encoding="utf-8"), indent=1); print("split manifest: written")
    print(f"  seed {man['seed']}; tune {len(man['tune'])} requests, held-out {len(man['heldout'])}; split sha256 {man['split_sha256'][:16]}...; "
          f"labels sha256 {man['labels_sha256'][:16]}... ({'same file as now' if man['labels_sha256'] == labels_sha else 'LABELS FILE CHANGED SINCE THE SPLIT'})")
    print("  tune ids: " + " ".join(man["tune"]))
    for half, detail in (("tune", True), ("heldout", False)):
        ids = set(man[half]); print(f"{half}:")
        report("product", [e for e in prod if e["query_id"] in ids], detail)
        report("tender ", [e for e in tend if e["query_id"] in ids], detail)


if __name__ == "__main__":
    main(sys.argv[1:5])
