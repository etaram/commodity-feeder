"""tools/eval_score.py on a tiny fixture (fictional companies)."""
import json

from tools import eval_score as es


def _row(qid, rank, supplier, query, set_="product"):
    return {"set": set_, "query_id": qid, "query": query, "rank": rank, "supplier": supplier, "country": "XXX", "type": "", "evidence": "", "website": "", "has_contact": False}


def _ver(qid, rank, bucket, set_="product"):
    return {"set": set_, "query_id": qid, "rank": rank, "bucket": bucket, "reason": f"reason {qid}-{rank}", "evidence_basis": "x"}


def fixture():
    rows, ver, lab = [], [], {}
    # Q01: 6 rows. supported: relevant, relevant, irrelevant; plausible: partly, irrelevant, cannot_tell
    plan = [("supported", "relevant"), ("supported", "relevant"), ("supported", "irrelevant"), ("plausible", "partly"), ("plausible", "irrelevant"), ("plausible", "cannot_tell")]
    for i, (b, l) in enumerate(plan, 1):
        rows.append(_row("Q01", i, f"Co {i}", "diesel generator")); ver.append(_ver("Q01", i, b)); lab[("Q01", i)] = (l, f"why {i}")
    # Q02: 2 rows, both irrelevant (a request with no relevant result in the top 10)
    for i, b in enumerate(["plausible", "related"], 1):
        rows.append(_row("Q02", i, f"Wrong {i}", "urea")); ver.append(_ver("Q02", i, b)); lab[("Q02", i)] = ("irrelevant", "cosmetics")
    # Q03 returned nothing (known from the summary only); Q04: one row, not labelled
    rows.append(_row("Q04", 1, "Unseen", "cement")); ver.append(_ver("Q04", 1, "supported"))
    # tenders: T01 goods (1 relevant), T02 non-goods with 2 suppliers returned, T03 non-goods with none, T04 mixed overruled to non_goods
    rows.append(_row("T01", 1, "Glove Maker", "Supply of gloves", "tender")); ver.append(_ver("T01", 1, "supported", "tender")); lab[("T01", 1)] = ("relevant", "")
    for i in (1, 2):
        rows.append(_row("T02", i, f"Agri {i}", "Agriculture value chains development", "tender")); ver.append(_ver("T02", i, "plausible", "tender")); lab[("T02", i)] = ("irrelevant", "no goods bought")
    rows.append(_row("T04", 1, "Road Co", "Framework agreement for road repairs", "tender")); ver.append(_ver("T04", 1, "plausible", "tender")); lab[("T04", 1)] = ("irrelevant", "works")
    tenders = [{"query_id": "T01", "title": "Supply of gloves", "stratum": "goods"}, {"query_id": "T02", "title": "Agriculture value chains development", "stratum": "non_goods"},
               {"query_id": "T03", "title": "Consultancy for an audit", "stratum": "non_goods"}, {"query_id": "T04", "title": "Framework agreement for road repairs", "stratum": "mixed"}]
    summary = {"product": {"per_query": [{"id": q} for q in ("Q01", "Q02", "Q03", "Q04")]}, "tender": {"per_query": [{"id": q} for q in ("T01", "T02", "T03", "T04")]}}
    return rows, ver, lab, tenders, summary


def test_product_set_precision_and_buckets():
    rows, ver, lab, tenders, summary = fixture()
    p = es.score(rows, ver, lab, tenders, summary)["product"]
    assert p["requests"] == 4 and p["rows"] == 9 and p["labelled_rows"] == 8
    # pooled at 5: Q01 top 5 = 2 relevant, 1 partly, 2 irrelevant; Q02 = 2 irrelevant; Q04 unlabelled
    at5 = p["pooled"][5]
    assert (at5["relevant"], at5["partly"], at5["irrelevant"], at5["judged"], at5["unlabelled"]) == (2, 1, 4, 7, 1)
    assert abs(at5["precision"] - 2 / 7) < 1e-9 and abs(at5["precision_with_partly"] - 3 / 7) < 1e-9
    # cannot_tell is outside the denominator
    assert p["pooled"][10]["cannot_tell"] == 1 and p["pooled"][10]["judged"] == 7
    # mean over requests: Q01 2/5, Q02 0, Q03 and Q04 have no judged rows
    assert abs(p["macro"][5] - 0.2) < 1e-9
    q1 = next(e for e in p["per_query"] if e["query_id"] == "Q01")
    assert abs(q1["p@5"]["precision"] - 0.4) < 1e-9 and abs(q1["p@25"]["precision"] - 0.4) < 1e-9
    # what share of "supported" is really relevant
    assert abs(p["per_bucket"]["supported"]["precision"] - 2 / 3) < 1e-9 and p["per_bucket"]["supported"]["unlabelled"] == 1
    assert p["per_bucket"]["plausible"]["precision"] == 0 and p["per_bucket"]["plausible"]["judged"] == 3
    assert list(p["per_bucket"]) == ["supported", "plausible", "related"]


def test_zero_relevant_share_counts_empty_requests_and_skips_unlabelled():
    rows, ver, lab, tenders, summary = fixture()
    p = es.score(rows, ver, lab, tenders, summary)["product"]
    # decided: Q01 (has relevant), Q02 (none relevant), Q03 (returned nothing); Q04 is not labelled yet
    assert p["requests_decided_for_top10"] == 3 and p["requests_with_no_relevant_in_top10"] == 2 and p["requests_with_no_rows"] == 1
    assert abs(p["share_no_relevant_in_top10"] - 2 / 3) < 1e-9
    # without the summary the empty request is unknown
    assert es.score(rows, ver, lab)["product"]["requests"] == 3


def test_false_positives_are_ordered_worst_first_with_the_matcher_reason():
    rows, ver, lab, tenders, summary = fixture()
    fp = es.score(rows, ver, lab, tenders, summary)["product"]["worst_false_positives"]
    assert [(x["query_id"], x["rank"], x["bucket"]) for x in fp] == [("Q01", 3, "supported"), ("Q02", 1, "plausible"), ("Q01", 5, "plausible"), ("Q02", 2, "related")]
    assert fp[0]["matcher_reason"] == "reason Q01-3" and fp[1]["labeller_reason"] == "cosmetics"
    many_rows = [_row("Q09", i, f"C{i}", "x") for i in range(1, 41)]
    many = es.score(many_rows, [_ver("Q09", i, "supported") for i in range(1, 41)], {("Q09", i): ("irrelevant", "") for i in range(1, 41)})["product"]
    assert len(many["worst_false_positives"]) == 30 and many["false_positives_total"] == 40


def test_tender_set_is_reported_separately_with_the_non_goods_share():
    rows, ver, lab, tenders, summary = fixture()
    res = es.score(rows, ver, lab, tenders, summary)
    t = res["tender"]
    assert t["requests"] == 4 and t["rows"] == 4 and res["product"]["rows"] == 9
    assert (t["non_goods_tenders"], t["non_goods_tenders_with_any_supplier"], t["non_goods_rows_returned"]) == (2, 1, 2)
    assert t["share_non_goods_with_any_supplier"] == 0.5
    assert t["per_stratum"]["goods"][10]["precision"] == 1 and t["per_stratum"]["non_goods"][10]["precision"] == 0
    # the labeller overrules a stratum with a rank 0 line
    t2 = es.score(rows, ver, lab, tenders, summary, {"T04": "non_goods"})["tender"]
    assert (t2["non_goods_tenders"], t2["non_goods_tenders_with_any_supplier"]) == (3, 2)


def test_owner_verdicts_are_matched_on_the_asked_text():
    rows, ver, lab, tenders, summary = fixture()
    human = [{"supplier": "agri 1", "product": "agriculture", "label": "no", "asked": "Agriculture value chains development"},
             {"supplier": "Co 1", "product": "diesel generator", "label": "yes", "asked": ""}, {"supplier": "Nobody", "product": "x", "label": "no", "asked": "y"}]
    h = es.score(rows, ver, lab, tenders, summary, human=human)["owner_ground_truth"]
    assert h["owner_verdicts"] == 3 and h["by_label"] == {"no": 2, "yes": 1} and h["matched_rows"] == 2
    assert [(x["query_id"], x["rank"], x["bucket"]) for x in h["owner_no_still_returned"]] == [("T02", 1, "plausible")]


def test_files_cli_and_label_formats(tmp_path, capsys):
    rows, ver, lab, tenders, summary = fixture()
    w = lambda name, recs: (tmp_path / name).write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    w("rows.jsonl", rows), w("verdicts.jsonl", ver), w("tenders.jsonl", tenders)
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    recs = [{"query_id": q, "rank": r, "label": l, "reason": why} for (q, r), (l, why) in lab.items()]
    w("labels.jsonl", recs + [{"query_id": "T04", "rank": 0, "label": "non_goods", "reason": "road works"}, {"query_id": "Q01", "rank": 9, "label": "maybe"}])
    (tmp_path / "labels.csv").write_text("query_id,rank,label,reason\n" + "".join(f"{x['query_id']},{x['rank']},{x['label'].upper()},\"{x['reason']}\"\n" for x in recs), encoding="utf-8")
    l1, strata, bad = es.read_labels(tmp_path / "labels.jsonl")
    l2, _, _ = es.read_labels(tmp_path / "labels.csv")
    assert l1 == lab and {k: v[0] for k, v in l2.items()} == {k: v[0] for k, v in lab.items()} and strata == {"T04": "non_goods"} and len(bad) == 1
    args = [str(tmp_path / n) for n in ("rows.jsonl", "verdicts.jsonl", "labels.jsonl")] + ["--tenders", str(tmp_path / "tenders.jsonl"), "--summary", str(tmp_path / "summary.json")]
    assert es.main(args) == 0
    out = capsys.readouterr().out
    assert "=== PRODUCT SET: 4 requests, 9 rows returned, 8 labelled ===" in out and "=== TENDER SET" in out
    assert "supported  67% relevant (2 of 3 judged" in out
    assert "requests with no relevant result in the top 10: 2 of 3 (67%)" in out
    assert "any supplier was returned: 2 of 3 (67%)" in out
    assert "matcher: reason Q01-3 | labeller: why 3" in out
    assert es.main(args + ["--json"]) == 0 and json.loads(capsys.readouterr().out)["tender"]["non_goods_tenders"] == 3
