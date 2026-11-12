"""Scheduler: only a run queued GHOST_H hours with no job at all is ignored (GitHub ghost); legitimate old
pending/waiting runs, queued runs with a job and running jobs still count; an API failure still means 'skip'."""
import datetime as dt
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("sinder_sched", Path(__file__).resolve().parents[1] / "deploy/ops/scheduler/sched.py")
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
OLD = "2026-11-11T20:37:19Z"


def mk(runs, jobs, fail_jobs=False):
    def api(u, tok=None):
        if "/jobs" in u:
            if fail_jobs:
                return 500, None
            return 200, {"total_count": jobs.get(int(u.split("runs/")[1].split("/")[0]), 0)}
        rr = runs.get(u.split("status=")[1].split("&")[0], [])
        return 200, {"total_count": len(rr), "workflow_runs": rr}
    return api


def fresh():
    return (dt.datetime.now(S.UTC) - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_cases(monkeypatch):
    monkeypatch.setattr(S, "log", lambda m: None)
    cases = [
        ({"queued": [{"id": 1, "created_at": OLD}]}, {1: 0}, ("queued",), 0),            # the ghost
        ({"queued": [{"id": 2, "created_at": OLD}]}, {2: 1}, ("queued",), 1),            # old but has a job
        ({"pending": [{"id": 3, "created_at": OLD}]}, {}, ("pending",), 1),             # concurrency queue
        ({"waiting": [{"id": 4, "created_at": OLD}]}, {}, ("waiting",), 1),             # approval
        ({"queued": [{"id": 5, "created_at": fresh()}]}, {5: 0}, ("queued",), 1),       # just queued
        ({"in_progress": [{"id": 6, "created_at": OLD}]}, {}, ("in_progress",), 1),     # running
    ]
    for runs, jobs, states, want in cases:
        monkeypatch.setattr(S, "api", mk(runs, jobs))
        assert S.waiting_runs("w.yml", "t", states) == want, (runs, want)
    monkeypatch.setattr(S, "api", mk({"queued": [{"id": 7, "created_at": OLD}]}, {}, fail_jobs=True))
    assert S.waiting_runs("w.yml", "t", ("queued",)) is None
