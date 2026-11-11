"""F19 source integrity: a failed collector must not look like success (leads/source_status.py, leads/run.py).
Fake sources only: one that raises, one that is refused, one that is throttled, one that returns zero rows, one that
halves, one that is stale. Everything is written under a temporary folder. Run: python -m pytest tests/test_source_status.py -q"""
import datetime as dt
import json
import sys
import types

import pytest

from leads import common, health, run, source_status as S

T0 = dt.datetime(2026, 11, 10, 8, 0)


def rows(n, tag="a"):
    return [{"id": f"{tag}{i}", "title": f"notice {i}", "source": "fake"} for i in range(n)]


@pytest.fixture()
def leads_dir(tmp_path, monkeypatch):
    d = tmp_path / "leads"
    (d / "partial").mkdir(parents=True)
    for mod in (common, run, health):
        monkeypatch.setattr(mod, "LEADS", d)
    for mod in (common, run):
        monkeypatch.setattr(mod, "PARTIAL", d / "partial")
    monkeypatch.delenv("LEADS_ALLOW_SHRINK", raising=False)
    return d


def fake_source(monkeypatch, name, fetch):
    """Registers leads.<name> as a collector module whose fetch() is the given function."""
    m = types.ModuleType(f"leads.{name}")
    m.fetch = fetch
    monkeypatch.setitem(sys.modules, f"leads.{name}", m)
    monkeypatch.setattr(run, "NEW_MODULES", set(run.NEW_MODULES) | {name})
    return m


def run_cli(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["leads.run", *args])
    return run.main()


def status(d, name):
    j = json.loads((d / "source_status.json").read_text())
    return next(s for s in j["sources"] if s["source"] == name)


def snapshot(d, name):
    return json.loads((d / "partial" / f"{name}.json").read_text())


class HttpError(Exception):
    def __init__(self, code, msg="boom"):
        super().__init__(msg)
        self.response = types.SimpleNamespace(status_code=code)


def test_good_run_is_ok_and_becomes_the_baseline(leads_dir):
    e = S.record_result("fake_ok", rows(10), {"pages": 1}, now=T0)
    assert e["status"] == "OK" and e["rows"] == 10 and e["rows_last_good"] == 10 and e["last_good_at"] == "2026-11-10T08:00" and e["error_class"] == ""
    assert len(snapshot(leads_dir, "fake_ok")["rows"]) == 10
    j = json.loads((leads_dir / "source_status.json").read_text())
    assert j["not_ok"] == 0 and set(j["sources"][0]) >= {"source", "status", "rows", "rows_last_good", "last_good_at", "error_class"}


def test_source_that_raises_is_down_and_the_previous_snapshot_survives(leads_dir, monkeypatch):
    S.record_result("fake_raise", rows(8), now=T0)
    before = (leads_dir / "partial" / "fake_raise.json").read_bytes()

    def boom():
        raise RuntimeError("connection reset while reading https://example.test/api?token=SECRET-TOKEN-123 " + "x" * 5000)
    fake_source(monkeypatch, "fake_raise", boom)
    with pytest.raises(RuntimeError):
        run_cli(monkeypatch, "--source", "fake_raise")
    e = status(leads_dir, "fake_raise")
    assert e["status"] == "DOWN" and e["rows"] == 0 and e["rows_last_good"] == 8 and e["last_good_at"] == "2026-11-10T08:00"
    assert e["error_class"] == "RuntimeError", "the class of the error, never its message"
    text = (leads_dir / "source_status.json").read_text()
    assert "SECRET-TOKEN-123" not in text and "example.test" not in text and len(text) < 2000
    assert (leads_dir / "partial" / "fake_raise.json").read_bytes() == before, "the previous good snapshot is untouched"
    assert (leads_dir / "error_fake_raise.txt").exists(), "the traceback file of the run is still written"


def test_http_denial_and_throttling_have_their_own_status(leads_dir):
    S.record_result("fake_denied", rows(5), now=T0)
    assert S.record_failure("fake_denied", HttpError(403), now=T0)["status"] == "DENIED"
    assert status(leads_dir, "fake_denied")["error_class"] == "HttpError:403"
    assert S.record_failure("fake_denied", HttpError(401), now=T0)["status"] == "DENIED"
    assert S.record_failure("fake_limited", HttpError(429), now=T0)["status"] == "RATE_LIMITED"
    assert S.record_failure("fake_limited", RuntimeError("HTTP 429 Too Many Requests"), now=T0)["error_class"] == "RuntimeError:429"
    assert S.record_failure("fake_limited", HttpError(500), now=T0)["status"] == "DOWN"
    assert len(snapshot(leads_dir, "fake_denied")["rows"]) == 5, "a refusal keeps the previous snapshot"


def test_zero_rows_is_degraded_and_never_overwrites_a_good_snapshot(leads_dir, monkeypatch):
    fake_source(monkeypatch, "fake_zero", lambda: (rows(12), {"pages": 2}))
    run_cli(monkeypatch, "--source", "fake_zero")
    assert status(leads_dir, "fake_zero")["status"] == "OK"
    before = (leads_dir / "partial" / "fake_zero.json").read_bytes()
    fake_source(monkeypatch, "fake_zero", lambda: ([], {"pages": 0}))
    run_cli(monkeypatch, "--source", "fake_zero")   # the collector did not raise: today this looked like a success
    e = status(leads_dir, "fake_zero")
    assert e["status"] == "DEGRADED" and e["rows"] == 0 and e["rows_last_good"] == 12 and e["error_class"] == "zero_rows"
    assert (leads_dir / "partial" / "fake_zero.json").read_bytes() == before, "the previous snapshot survives an empty run"
    assert len(snapshot(leads_dir, "fake_zero")["rows"]) == 12


def test_zero_rows_with_no_history_is_not_ok(leads_dir):
    e = S.record_result("fake_never", [], now=T0)
    assert e["status"] != "OK" and e["rows_last_good"] == 0


def test_halved_rows_are_degraded_with_the_new_data_kept_and_a_warning(leads_dir):
    S.record_result("fake_half", rows(100), now=T0)
    e = S.record_result("fake_half", rows(49, "b"), now=T0 + dt.timedelta(hours=2))
    assert e["status"] == "DEGRADED" and e["rows"] == 49 and e["rows_last_good"] == 100 and e["error_class"] == "rows_dropped"
    assert "100" in e["warning"] and "49" in e["warning"]
    assert len(snapshot(leads_dir, "fake_half")["rows"]) == 49, "the new data is kept"
    assert e["last_good_at"] == "2026-11-10T08:00", "a halved run is not a good run"
    assert S.record_result("fake_half", rows(50, "c"), now=T0 + dt.timedelta(hours=4))["status"] == "OK", "exactly half is not below half"
    S.record_result("fake_half", rows(10, "d"), now=T0 + dt.timedelta(hours=6))
    assert S.accept("fake_half", now=T0 + dt.timedelta(hours=6))["rows_last_good"] == 10, "an owner can accept a real drop as the new baseline"
    assert status(leads_dir, "fake_half")["status"] == "OK"


def test_stale_when_the_last_good_run_is_older_than_the_cadence(leads_dir):
    S.record_result("ted", rows(20), now=T0)        # a light source: expected every 2 hours, stale after 8
    S.record_result("fake_heavy", rows(20), now=T0)  # default cadence: 36 hours
    S.refresh(now=T0 + dt.timedelta(hours=7))
    assert status(leads_dir, "ted")["status"] == "OK"
    S.refresh(now=T0 + dt.timedelta(hours=9))
    assert status(leads_dir, "ted")["status"] == "STALE" and status(leads_dir, "ted")["rows_last_good"] == 20
    assert status(leads_dir, "fake_heavy")["status"] == "OK"
    S.refresh(now=T0 + dt.timedelta(hours=37))
    assert status(leads_dir, "fake_heavy")["status"] == "STALE"
    # empty runs do not refresh last_good_at: a source that keeps returning nothing goes stale
    S.record_result("ted", [], now=T0 + dt.timedelta(hours=40))
    assert status(leads_dir, "ted")["status"] == "STALE"
    # a failure keeps its own status (it says more than "stale"), and a good run clears everything
    assert S.record_failure("ted", HttpError(403), now=T0 + dt.timedelta(hours=41))["status"] == "DENIED"
    assert S.record_result("ted", rows(21), now=T0 + dt.timedelta(hours=42))["status"] == "OK"
    j = json.loads((leads_dir / "source_status.json").read_text())
    assert [s["status"] for s in j["sources"]].index("STALE") < [s["status"] for s in j["sources"]].index("OK"), "sources that are not OK are listed first"


def test_first_run_takes_the_baseline_from_the_snapshot_already_on_disk(leads_dir):
    (leads_dir / "partial" / "fake_old.json").write_text(json.dumps({"source": "fake_old", "rows": rows(30), "meta": {}, "ran": "2026-11-10T06:00"}))
    e = S.record_result("fake_old", [], now=T0)
    assert e["status"] == "DEGRADED" and e["rows_last_good"] == 30 and len(snapshot(leads_dir, "fake_old")["rows"]) == 30


def test_statuses_are_the_documented_set(leads_dir):
    S.record_result("a", rows(3), now=T0); S.record_result("b", [], now=T0); S.record_failure("c", ValueError("x"), now=T0)
    j = json.loads((leads_dir / "source_status.json").read_text())
    assert {s["status"] for s in j["sources"]} <= set(S.STATUSES) and j["not_ok"] == 2


def test_merge_guard_refuses_an_empty_or_halved_merge_without_the_override(leads_dir):
    assert S.merge_guard(1000, now=T0)["rows_last_good"] == 1000
    assert S.merge_guard(600, now=T0)["status"] == "OK"
    with pytest.raises(S.MergeGuardError):
        S.merge_guard(0, now=T0)
    with pytest.raises(S.MergeGuardError):
        S.merge_guard(299, now=T0)
    m = json.loads((leads_dir / "source_status.json").read_text())["merge"]
    assert m["status"] == "DEGRADED" and m["rows_last_good"] == 600 and m["error_class"] == "merge_rows_dropped"
    assert S.merge_guard(299, allow=True, now=T0)["rows_last_good"] == 299, "the explicit override accepts it"
    with pytest.raises(S.MergeGuardError):
        S.merge_guard(0, now=T0)


def test_merge_exits_non_zero_and_writes_nothing_when_the_merged_list_is_empty(leads_dir, monkeypatch):
    written = []
    monkeypatch.setattr(run, "benchmarks", lambda: {})
    monkeypatch.setattr(run, "merge_tenders", lambda bm, seen: ([], []))
    monkeypatch.setattr(run, "write", lambda name, *a, **k: written.append(name))
    (leads_dir / "tenders.csv").write_text("id\nkept\n")
    with pytest.raises(S.MergeGuardError):
        run_cli(monkeypatch, "--merge")           # an uncaught exception: the process exits non-zero
    assert (leads_dir / "error_merge.txt").exists(), "leads.health turns the workflow run red on this file"
    assert not written and (leads_dir / "tenders.csv").read_text() == "id\nkept\n" and not (leads_dir / "seen.json").exists(), "no output was written"
    assert health.main() == 1, "the health step of the workflow fails"


def test_merge_override_flag_and_env(leads_dir, monkeypatch):
    assert S.allow_shrink(False) is False and S.allow_shrink(True) is True
    monkeypatch.setenv("LEADS_ALLOW_SHRINK", "1")
    assert S.allow_shrink(False) is True
    monkeypatch.setenv("LEADS_ALLOW_SHRINK", "0")
    assert S.allow_shrink(False) is False
