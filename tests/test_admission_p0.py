"""P0 from review 176: a validated complete-empty list must reach the merge input, and rows kept from parts of a
source that did not answer must not count as active. Goes through collector -> cache -> source_status -> PARTIAL -> merge."""
import json


def _isolate(tmp_path, monkeypatch):
    from leads import common, run, source_status
    leads = tmp_path / "leads"
    monkeypatch.setattr(common, "LEADS", leads)
    monkeypatch.setattr(common, "PARTIAL", leads / "partial")
    monkeypatch.setattr(common, "CACHE", leads / "cache")
    monkeypatch.setattr(run, "PARTIAL", leads / "partial")
    monkeypatch.setattr(run, "LEADS", leads)
    monkeypatch.setattr(run, "_rates", lambda: {"USD": 1.0, "ZAR": 0.055})
    monkeypatch.setattr(run, "_group_bench", lambda bm: {})
    return common, run, source_status


def _row(i, hub="", deadline="2099-12-31", country="ZAF"):
    rid = f"bf-{hub}-{i}" if hub else f"tn-{i}"
    return {"id": rid, "title": f"Supply of pipes {i}", "buyer": "B", "country": country, "deadline": deadline,
            "published": "2026-11-10", "link": f"https://x/{i}", "source": "t", "fetched": "2026-11-10"}


def _merged_ids(run, monkeypatch, sources):
    monkeypatch.setattr(run, "TENDER_SOURCES", sources)
    out, _ = run.merge_tenders({}, {})
    return {r.get("id") or r.get("ID") for r in out} if out and isinstance(out[0], dict) else out


def test_transnet_last_notice_cancelled_reaches_merge(tmp_path, monkeypatch):
    common, run, source_status = _isolate(tmp_path, monkeypatch)
    source_status.record_result("transnet", [_row(1)], {"new": 1, "complete_snapshot": 1})
    assert json.loads((common.PARTIAL / "transnet.json").read_text())["rows"]
    # next run: the only notice was cancelled upstream; the complete list is empty
    e = source_status.record_result("transnet", [], {"new": 0, "complete_snapshot": 1})
    assert e["status"] == "OK"
    assert json.loads((common.PARTIAL / "transnet.json").read_text())["rows"] == []
    monkeypatch.setattr(run, "TENDER_SOURCES", ["transnet"])
    out, _ = run.merge_tenders({}, {})
    assert out == []


def test_empty_without_complete_flag_keeps_last_good(tmp_path, monkeypatch):
    common, run, source_status = _isolate(tmp_path, monkeypatch)
    source_status.record_result("transnet", [_row(1)], {"new": 1})
    e = source_status.record_result("transnet", [], {"new": 0})          # a pull that may have failed silently
    assert e["status"] == "DEGRADED"
    assert len(json.loads((common.PARTIAL / "transnet.json").read_text())["rows"]) == 1


class _S:
    def __init__(self, answers):
        self.answers = answers

    def get(self, url, **k):
        hub = url.split("//")[1].split(".")[0]
        a = self.answers.get(hub)

        class R:
            status_code = 200 if a is not None else 503
            text = "<title>Hub</title>"

            def json(self_):
                return a
        return R()


def test_bonfire_stale_hub_rows_not_active(tmp_path, monkeypatch):
    common, run, source_status = _isolate(tmp_path, monkeypatch)
    from leads import bonfire
    monkeypatch.setattr(bonfire, "CACHE", common.CACHE)
    monkeypatch.setattr(bonfire, "HUBS", [("a", "A", "USA"), ("b", "B", "USA")])
    monkeypatch.setattr(bonfire, "_org", lambda s, h: "Org " + h)
    monkeypatch.setattr(bonfire.time, "sleep", lambda s: None)
    # earlier run: hub b had one open notice
    common.snapshot("bonfire", [dict(_row(1, "b", country="USA"), last_success=str(common.today()))])
    # this run: hub a answers with an empty complete list, hub b fails
    monkeypatch.setattr(bonfire, "session", lambda: _S({"a": {"success": True, "payload": {"projects": {}}}}))
    monkeypatch.setattr(bonfire, "parse", lambda js, hub, buyer, country, t: [])
    rows, meta = bonfire.fetch()
    assert meta["stale_rows"] == 1 and rows[0]["stale"] is True
    e = source_status.record_result("bonfire", rows, meta)
    assert e["status"] == "DEGRADED" and e["error_class"] == "partial_failure"
    monkeypatch.setattr(run, "TENDER_SOURCES", ["bonfire"])
    out, _ = run.merge_tenders({}, {})
    assert out == []                                                       # history kept, not active
    assert json.loads((common.PARTIAL / "bonfire.json").read_text())["rows"][0]["id"] == "bf-b-1"


def test_bonfire_stale_rows_expire(tmp_path, monkeypatch):
    common, run, source_status = _isolate(tmp_path, monkeypatch)
    from leads import bonfire
    monkeypatch.setattr(bonfire, "CACHE", common.CACHE)
    monkeypatch.setattr(bonfire, "HUBS", [("a", "A", "USA"), ("b", "B", "USA")])
    monkeypatch.setattr(bonfire, "_org", lambda s, h: "Org")
    monkeypatch.setattr(bonfire.time, "sleep", lambda s: None)
    common.snapshot("bonfire", [dict(_row(1, "b", country="USA"), last_success="2026-01-01")])
    monkeypatch.setattr(bonfire, "session", lambda: _S({"a": {"success": True}}))
    monkeypatch.setattr(bonfire, "parse", lambda js, hub, buyer, country, t: [])
    rows, meta = bonfire.fetch()
    assert rows == [] and meta["stale_rows"] == 0


def test_fresh_bonfire_row_is_active(tmp_path, monkeypatch):
    common, run, source_status = _isolate(tmp_path, monkeypatch)
    from leads import bonfire
    monkeypatch.setattr(bonfire, "CACHE", common.CACHE)
    monkeypatch.setattr(bonfire, "HUBS", [("a", "A", "USA")])
    monkeypatch.setattr(bonfire, "_org", lambda s, h: "Org")
    monkeypatch.setattr(bonfire.time, "sleep", lambda s: None)
    monkeypatch.setattr(bonfire, "session", lambda: _S({"a": {"success": True}}))
    monkeypatch.setattr(bonfire, "parse", lambda js, hub, buyer, country, t: [_row(7, "a", country="USA")])
    rows, meta = bonfire.fetch()
    e = source_status.record_result("bonfire", rows, meta)
    assert e["status"] == "OK"
    monkeypatch.setattr(run, "TENDER_SOURCES", ["bonfire"])
    out, _ = run.merge_tenders({}, {})
    assert len(out) == 1
