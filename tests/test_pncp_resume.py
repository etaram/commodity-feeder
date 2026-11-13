"""PNCP backfill resumes across runs (ChatGPT row 138): two budget-cut runs read disjoint pages; a failed page is not
checkpointed; the freshness lane runs every time."""
import json

import pytest

from leads import pncp


class R:
    def __init__(self, code, data=None, remaining=0):
        self.status_code = code; self._j = {"data": data or [], "paginasRestantes": remaining}

    def json(self):
        return self._j


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(pncp, "CACHE", tmp_path)
    monkeypatch.setattr(pncp, "PROGRESS", tmp_path / "pncp_progress.json")
    monkeypatch.setattr(pncp, "polite", lambda s: None)
    monkeypatch.setattr(pncp, "rolling", lambda name, rows, max_age_days=0: (rows, None))
    monkeypatch.setattr(pncp, "MODES", {6: "Pregão eletrônico", 4: "Concorrência eletrônica"})
    calls = []

    class S:
        fail = set()

        def get(self, url, params=None, timeout=0):
            key = (params["dataInicial"], params["codigoModalidadeContratacao"], params["pagina"])
            calls.append(key)
            if key in S.fail:
                return R(503)
            back = params["dataInicial"] != fresh_d0()
            n = 5 if back else 1        # backfill: 5 pages per modality; fresh: 1
            p = params["pagina"]
            return R(200, [{"numeroControlePNCP": f"{key}", "dataEncerramentoProposta": "2999-01-01"}], n - p)
    monkeypatch.setattr(pncp, "session", lambda: S())
    return S, calls


def fresh_d0():
    import datetime as dt
    return (pncp.today() - dt.timedelta(days=2)).strftime("%Y%m%d")


def run_with_budget(monkeypatch, pages_allowed):
    """budget cut after N backfill pages (time is mocked by counting)"""
    count = {"n": 0}
    real_lane = pncp._lane

    def lane(s, d0, d1, t, budget, start=(0, 1)):
        if d0 == fresh_d0():
            return real_lane(s, d0, d1, t, 10**6, start)
        clock = {"i": 0}
        orig = pncp.time.time

        def fake():
            clock["i"] += 1
            return orig() + (10**6 if clock["i"] > pages_allowed + 1 else 0)
        monkeypatch.setattr(pncp.time, "time", fake)
        try:
            return real_lane(s, d0, d1, t, budget, start)
        finally:
            monkeypatch.setattr(pncp.time, "time", orig)
    monkeypatch.setattr(pncp, "_lane", lane)


def test_two_cut_runs_read_disjoint_pages_then_complete(env, monkeypatch):
    S, calls = env
    run_with_budget(monkeypatch, 3)
    pncp.fetch()
    first = [c for c in calls if c[0] != fresh_d0()]
    calls.clear()
    pncp.fetch()
    second = [c for c in calls if c[0] != fresh_d0()]
    assert first and second and not set(first) & set(second)
    prog = json.loads((pncp.PROGRESS).read_text())
    assert prog["mi"] >= 0
    for _ in range(6):
        calls.clear(); pncp.fetch()
    assert json.loads(pncp.PROGRESS.read_text()).get("done_on")


def test_failed_page_is_read_again(env, monkeypatch):
    S, calls = env
    S.fail = set()
    d0 = (pncp.today() - __import__("datetime").timedelta(days=30)).strftime("%Y%m%d")
    S.fail = {(d0, 6, 2)}
    _, st = pncp.fetch()
    assert st["failed_pages"] == 1
    prog = json.loads(pncp.PROGRESS.read_text())
    assert (prog["mi"], prog["page"]) == (0, 2)
    S.fail = set(); calls.clear()
    pncp.fetch()
    assert (d0, 6, 2) in calls


def test_fresh_lane_runs_every_time(env, monkeypatch):
    S, calls = env
    for _ in range(2):
        calls.clear(); pncp.fetch()
        assert any(c[0] == fresh_d0() for c in calls)
