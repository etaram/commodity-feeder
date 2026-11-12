"""Health reporting for modules that write files instead of returning rows (audit 1f): their real volume comes from
the meta they return, an idle run is OK, and supplier-side modules keep their own status file. Meta samples are the
ones the runner logged on 11 Nov 2026 (run.log, run_suppliers.log). No network."""
import json

import pytest

from leads import common, registry, source_status as S

# what the modules returned in the runner logs of 11-12 Nov 2026
META = {
    "awards": {"days": 3, "notices": 3578},
    "grants": {"calls": 527, "grants.gov": 270, "EU": 256, "data.gov.il": 1},
    "markets": {"refreshed": 0, "due": 0},
    "importyeti": {"scanned": 0, "due": 681},
    "latam_awards": {"brazil": 881, "colombia": 174},
    "prozorro_awards": {"candidates": 3000, "awards": 2711},
    "ocdr": {"files": 0, "awards": 0, "contacts": 0, "pending": 0},
    "ext_awards": {},
    "wikidata_companies": {"countries": 0, "companies": 0, "cached": 202},
}


@pytest.fixture()
def leads_dir(tmp_path, monkeypatch):
    d = tmp_path / "leads"
    (d / "partial").mkdir(parents=True)
    monkeypatch.setattr(common, "LEADS", d)
    monkeypatch.setattr(common, "PARTIAL", d / "partial")
    return d


def _rec(name):
    return S.record_result(name, [], META[name], save_fn=lambda *a: (_ for _ in ()).throw(AssertionError("no snapshot for file writers")))


def test_false_degraded_are_ok(leads_dir):
    assert _rec("awards")["status"] == "OK" and _rec("awards")["rows"] == 3578
    assert _rec("grants")["rows"] == 527
    m = _rec("markets")
    assert m["status"] == "OK" and "nothing due" in m["warning"]


def test_importyeti_with_due_work_and_nothing_scanned_stays_degraded(leads_dir):
    e = _rec("importyeti")
    assert e["status"] == "DEGRADED" and e["error_class"] == "zero_work" and "due 681" in e["warning"]


def test_supplier_modules_report_rows_in_their_own_file(leads_dir):
    assert _rec("latam_awards")["rows"] == 1055
    assert _rec("prozorro_awards")["rows"] == 2711
    assert _rec("ocdr")["status"] == "OK"            # nothing pending: idle, not a failure
    assert _rec("ext_awards")["status"] == "OK"      # both feeds fresh: idle
    assert _rec("wikidata_companies")["status"] == "OK"
    sup = json.loads((leads_dir / S.SUPPLIER_FILE).read_text())
    names = {s["source"] for s in sup["sources"]}
    assert {"latam_awards", "prozorro_awards", "ocdr", "ext_awards", "wikidata_companies"} <= names
    assert not (leads_dir / S.FILE).exists()   # leads.yml's file is not touched by the suppliers run


def test_tender_module_returning_rows_unchanged(leads_dir):
    e = S.record_result("kenya", [{"id": "1"}], {"new": 1}, save_fn=lambda *a: None)
    assert e["status"] == "OK" and e["rows"] == 1 and "kind" not in e


def test_registry_has_no_ghost_modules_and_maps_backlog():
    assert "georgia" not in registry.IMPLEMENTED and "ecuador" not in registry.IMPLEMENTED
    assert registry.BACKLOG["S36"][3] == "lei" and registry.BACKLOG["S37"][3] == "gdelt" and registry.BACKLOG["S39"][3] == "attention"
    from leads import run
    assert "georgia" not in run.NEW_MODULES and "ecuador" not in run.NEW_MODULES
