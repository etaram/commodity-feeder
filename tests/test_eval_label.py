"""tools/eval_label.py with a fake HTTP layer (fictional companies, no network)."""
import json

import pytest

from tools import eval_label as el
from tools import eval_score as es


def _row(qid, rank, set_="product", query="diesel generator", **extra):
    return {"set": set_, "query_id": qid, "query": query, "rank": rank, "supplier": f"Co {qid}-{rank}", "country": "XXX", "type": "manufacturer",
            "evidence": f"makes things {rank}", "website": "https://example.invalid", "has_contact": True, **extra}


def _write(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return str(path)


def _ok(items):
    return 200, {"content": [{"type": "text", "text": json.dumps(items)}], "usage": {"input_tokens": 100, "output_tokens": 20}, "stop_reason": "end_turn"}


class Fake:
    """Answers every company 'relevant' (and a tender 'goods') unless a scripted reply is queued. Records the payloads."""
    def __init__(self, script=None):
        self.script, self.payloads = list(script or []), []

    def __call__(self, payload, api_key):
        self.payloads.append(payload)
        if self.script:
            return self.script.pop(0)
        user = payload["messages"][0]["content"]
        ranks = [json.loads(line)["rank"] for line in user.splitlines() if line.startswith("{")]
        items = [{"rank": r, "label": "relevant", "reason": "makes it"} for r in ranks]
        if '"rank": 0' in user:
            items.insert(0, {"rank": 0, "label": "goods", "reason": "buys gloves"})
        return _ok(items)


def _run(tmp_path, rows, tenders=None, fake=None, **kw):
    said = []
    rows_p = _write(tmp_path / "rows.jsonl", rows)
    ten_p = _write(tmp_path / "tenders.jsonl", tenders) if tenders is not None else None
    out = tmp_path / "labels.jsonl"
    fake = fake or Fake()
    code = el.run(rows_p, ten_p, str(out), transport=fake, sleep=lambda s: None, say=said.append, **kw)
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
    return code, lines, fake, "\n".join(said)


def test_verdict_fields_never_reach_the_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rows = [_row("Q01", i, bucket="SECRETBUCKET", reason="SECRETREASON", evidence_basis="SECRETBASIS", stratum="SECRETSTRATUM", score=0.93) for i in (1, 2)]
    rows += [_row("T01", 1, "tender", "Supply of gloves", bucket="SECRETBUCKET")]
    tenders = [{"query_id": "T01", "title": "Supply of gloves", "sector": "Health", "stratum": "SECRETSTRATUM", "derivation": {"route": "SECRETROUTE"}, "match_rule": "SECRETRULE"}]
    code, lines, fake, said = _run(tmp_path, rows, tenders)
    assert code == 0 and len(fake.payloads) == 2
    sent = json.dumps(fake.payloads)
    assert "SECRET" not in sent and "0.93" not in sent
    assert "Co Q01-1" in sent and "makes things 2" in sent and "Supply of gloves" in sent and "Health" in sent
    # each company line carries exactly the seven allowed fields
    for p in fake.payloads:
        for line in p["messages"][0]["content"].splitlines():
            if line.startswith("{"):
                assert set(json.loads(line)) == set(el.ROW_FIELDS)
    # the public output has counts only
    assert "Co Q01" not in said and "makes" not in said


def test_output_format_is_what_the_scorer_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    code, lines, _, _ = _run(tmp_path, [_row("Q01", 2), _row("Q01", 1)])
    assert lines == [{"set": "product", "query_id": "Q01", "rank": 1, "label": "relevant", "reason": "makes it"},
                     {"set": "product", "query_id": "Q01", "rank": 2, "label": "relevant", "reason": "makes it"}]
    labels, strata, bad = es.read_labels(str(tmp_path / "labels.jsonl"))
    assert labels == {("Q01", 1): ("relevant", "makes it"), ("Q01", 2): ("relevant", "makes it")} and not strata and not bad


def test_invalid_reply_and_http_errors_are_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    good = [{"rank": 1, "label": "Irrelevant", "reason": "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"}]
    fake = Fake([(429, {}), (200, {"content": [{"type": "text", "text": "sorry, here you go: not json"}], "usage": {"input_tokens": 5, "output_tokens": 5}}),
                 _ok(good)])
    code, lines, fake, said = _run(tmp_path, [_row("Q01", 1)], fake=fake)
    assert code == 0 and len(fake.payloads) == 3
    assert lines[0]["label"] == "irrelevant" and len(lines[0]["reason"].split()) == 14
    assert "API calls: 3" in said and "invalid replies: 1" in said and "input tokens: 105" in said


@pytest.mark.parametrize("items", [
    [{"rank": 1, "label": "relevant", "reason": ""}],                                                    # rank 2 missing
    [{"rank": 1, "label": "great", "reason": ""}, {"rank": 2, "label": "relevant", "reason": ""}],       # illegal label
    [{"rank": 1, "label": "goods", "reason": ""}, {"rank": 2, "label": "relevant", "reason": ""}],       # stratum word on a company
    [{"rank": 1, "label": "relevant", "reason": ""}, {"rank": 2, "label": "partly", "reason": ""}, {"rank": 3, "label": "partly", "reason": ""}],  # a rank never asked
])
def test_a_request_that_stays_invalid_is_not_written(tmp_path, monkeypatch, items):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    code, lines, fake, said = _run(tmp_path, [_row("Q01", 1), _row("Q01", 2)], fake=Fake([_ok(items)] * 3))
    assert code == 1 and lines == [] and len(fake.payloads) == 3 and "requests failed after 3 tries: 1" in said


def test_resumes_and_redoes_a_half_written_request(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rows = [_row("Q01", 1), _row("Q01", 2), _row("Q02", 1), _row("Q03", 1), _row("Q03", 2)]
    code, lines, fake, _ = _run(tmp_path, rows, limit=1)
    assert code == 0 and len(fake.payloads) == 1 and {x["query_id"] for x in lines} == {"Q01"}
    # a half-written Q03 (one of two ranks) must be done again, Q01 must not
    with open(tmp_path / "labels.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"set": "product", "query_id": "Q03", "rank": 1, "label": "partly", "reason": "old"}) + "\n")
    code, lines, fake, said = _run(tmp_path, rows)
    assert code == 0 and len(fake.payloads) == 2 and "already labelled: 1" in said
    assert sorted((x["query_id"], x["rank"]) for x in lines) == [("Q01", 1), ("Q01", 2), ("Q02", 1), ("Q03", 1), ("Q03", 2)]
    assert all(x["reason"] != "old" for x in lines)
    code, lines, fake, _ = _run(tmp_path, rows)
    assert code == 0 and fake.payloads == [] and len(lines) == 5


def test_tender_gets_a_rank_zero_line(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rows = [_row("T02", i, "tender", "Road repairs") for i in (1, 2)]
    reply = [{"rank": 0, "label": "non_goods", "reason": "road works"}] + [{"rank": i, "label": "irrelevant", "reason": "no goods bought"} for i in (1, 2)]
    code, lines, fake, said = _run(tmp_path, rows, [{"query_id": "T02", "title": "Road repairs", "sector": "Works", "stratum": "goods"}], fake=Fake([_ok(reply)]))
    assert code == 0 and lines[0] == {"set": "tender", "query_id": "T02", "rank": 0, "label": "non_goods", "reason": "road works"}
    assert "rows labelled: 2" in said and "tender buys non_goods 1" in said
    labels, strata, bad = es.read_labels(str(tmp_path / "labels.jsonl"))
    assert strata == {"T02": "non_goods"} and len(labels) == 2 and not bad
    # a tender reply without the rank 0 object is invalid; a product request never asks for one
    assert el.TENDER_ASK in fake.payloads[0]["messages"][0]["content"]
    with pytest.raises(ValueError):
        el.parse_reply(json.dumps(reply[1:]), [1, 2], True)


def test_more_than_forty_rows_are_sent_in_batches(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    rows = [_row("T01", i, "tender", "Supply of gloves") for i in range(1, 46)]
    code, lines, fake, said = _run(tmp_path, rows, [])
    assert code == 0 and len(fake.payloads) == 2 and len(lines) == 46 and "2 API calls" in said
    first, second = (p["messages"][0]["content"] for p in fake.payloads)
    assert first.count("\n{") == 40 and second.count("\n{") == 5
    assert el.TENDER_ASK in first and el.TENDER_ASK not in second and "already decided that it buys: goods" in second


@pytest.mark.parametrize("name", ["verdicts.jsonl", "human_labels.jsonl", "summary.json", "other.jsonl"])
def test_refuses_any_input_but_the_two_named_files(tmp_path, name, capsys):
    bad = _write(tmp_path / name, [_row("Q01", 1)])
    rows = _write(tmp_path / "rows.jsonl", [_row("Q01", 1)])
    out = str(tmp_path / "labels.jsonl")
    with pytest.raises(el.Refused):
        el.run(bad, None, out, dry_run=True, say=lambda s: None)
    with pytest.raises(el.Refused):
        el.run(rows, bad, out, dry_run=True, say=lambda s: None)
    assert el.main(["--rows", bad, "--out", out, "--dry-run"]) == 2
    assert "refused" in capsys.readouterr().out


def test_refuses_verdicts_behind_a_symlink_and_as_output(tmp_path):
    real = _write(tmp_path / "verdicts.jsonl", [_row("Q01", 1)])
    sub = tmp_path / "alias"
    sub.mkdir()
    (sub / "rows.jsonl").symlink_to(real)
    with pytest.raises(el.Refused):
        el.run(str(sub / "rows.jsonl"), None, str(tmp_path / "labels.jsonl"), dry_run=True, say=lambda s: None)
    rows = _write(tmp_path / "rows.jsonl", [_row("Q01", 1)])
    with pytest.raises(el.Refused):
        el.run(rows, None, real, dry_run=True, say=lambda s: None)


def test_dry_run_calls_nothing_and_masks_company_text(tmp_path):
    code, lines, fake, said = _run(tmp_path, [_row("Q01", 1), _row("Q02", 1)], dry_run=True)
    assert code == 0 and fake.payloads == [] and lines == []
    assert "to label now: 2 requests, 2 rows, 2 API calls" in said and "<supplier>" in said
    assert "Co Q01" not in said and "makes things" not in said and "example.invalid" not in said


def test_a_refused_key_stops_the_run_without_retrying(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    code, lines, fake, said = _run(tmp_path, [_row("Q01", 1), _row("Q02", 1)], fake=Fake([(401, {"error": {"type": "authentication_error"}})]))
    assert code == 1 and lines == [] and len(fake.payloads) == 1 and "HTTP 401" in said
