"""OCDR completion state (ChatGPT row 118, F19): a publisher/year is done only after a complete read and an atomic
write; failures, oversize files and time-cut reads stay retryable; a partial read never replaces a complete file."""
import gzip
import io
import json

import pytest

from leads import ocdr


class Resp:
    def __init__(self, status=200, body=b"", length=None):
        self.status_code = status
        self.headers = {"content-length": str(length if length is not None else len(body))}
        self.raw = io.BytesIO(body)

    def close(self):
        pass


def _gz(lines):
    return gzip.compress("".join(json.dumps(x) + "\n" for x in lines).encode())


REL = {"ocid": "x-1", "awards": [{"id": "a1", "suppliers": [{"name": "Acme Ltd", "id": "S1"}], "value": {"amount": 10, "currency": "USD"}}],
       "parties": [{"id": "S1", "name": "Acme Ltd", "roles": ["supplier"]}], "date": "2026-01-01"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ocdr, "PRIVATE", tmp_path)
    monkeypatch.setattr(ocdr, "OUT", tmp_path / "awards_ext")
    monkeypatch.setattr(ocdr, "STATE", tmp_path / "ocdr_state.json")
    monkeypatch.setattr(ocdr, "_publications", lambda s: [{"id": "7", "title": "Kenya: test", "iso": "KEN", "years": [2025]}])
    answers, calls = [], []

    class S:
        def get(self, url, **kw):
            calls.append(url)
            return answers.pop(0)
    monkeypatch.setattr(ocdr, "session", lambda: S())
    return answers, calls, tmp_path


def state(tmp):
    return json.loads((tmp / "ocdr_state.json").read_text())


def test_failed_download_stays_retryable(env, monkeypatch):
    answers, calls, tmp = env
    answers.append(Resp(503))
    _, st = ocdr.fetch()
    assert st["files"] == 0 and st["failed"] == 1 and "7/2025" not in state(tmp)["done"]
    assert state(tmp)["failed"]["7/2025"]["why"] == "http 503"
    # next run on the same day: backoff, no new download, still pending (not silently done)
    _, st2 = ocdr.fetch()
    assert len(calls) == 1 and st2["failed_total"] == 1 and "7/2025" not in state(tmp)["done"]
    # a day later it is tried again and completes
    import datetime as dt
    monkeypatch.setattr(ocdr, "today", lambda: dt.date.today() + dt.timedelta(days=1))
    answers.append(Resp(200, _gz([REL])))
    _, st3 = ocdr.fetch()
    assert len(calls) == 2 and st3["files"] == 1 and "7/2025" in state(tmp)["done"] and "7/2025" not in state(tmp)["failed"]
    assert (tmp / "awards_ext" / "ocdr_7_2025.jsonl").read_text().count("\n") >= 1


def test_too_large_not_done(env):
    answers, calls, tmp = env
    answers.append(Resp(200, b"", length=ocdr.MAX_BYTES + 1))
    _, st = ocdr.fetch()
    assert st["too_large"] == 1 and "7/2025" not in state(tmp)["done"]


def test_partial_keeps_last_good(env, monkeypatch):
    answers, calls, tmp = env
    out = tmp / "awards_ext"; out.mkdir()
    (out / "ocdr_7_2025.jsonl").write_text('{"good": 1}\n')
    st0 = {"pubs": [], "listed": "2999-01-01", "done": {}}
    (tmp / "ocdr_state.json").write_text(json.dumps(st0))
    monkeypatch.setattr(ocdr, "_publications", lambda s: [{"id": "7", "title": "Kenya: test", "iso": "KEN", "years": [2025]}])
    st0["listed"] = ""; (tmp / "ocdr_state.json").write_text(json.dumps(st0))
    real = ocdr._read
    monkeypatch.setattr(ocdr, "_read", lambda s, pid, y, iso, t, t_end: real(s, pid, y, iso, t, 0))   # budget already over
    answers.append(Resp(200, _gz([REL, REL])))
    _, st = ocdr.fetch()
    assert st["partial"] == 1 and "7/2025" not in state(tmp)["done"]
    assert (out / "ocdr_7_2025.jsonl").read_text() == '{"good": 1}\n'      # last complete file kept


def test_old_done_without_file_is_recovered(env):
    answers, calls, tmp = env
    (tmp / "ocdr_state.json").write_text(json.dumps({"pubs": [{"id": "7", "title": "Kenya: test", "iso": "KEN", "years": [2025]}],
                                                    "listed": "2999-01-01", "done": {"7/2025": "2026-11-01"}}))
    answers.append(Resp(200, _gz([REL])))
    _, st = ocdr.fetch()
    assert st["recovered"] == 1 and st["files"] == 1 and len(calls) == 1 and "7/2025" in state(tmp)["done"]


def _raw_gz(text):
    return gzip.compress(text.encode())


def test_malformed_award_line_is_not_a_valid_empty_result(env):
    answers, calls, tmp = env
    answers.append(Resp(200, _raw_gz('{"ocid": "x", "awards": [ broken\n')))
    _, st = ocdr.fetch()
    assert st["invalid"] == 1 and st["files"] == 0 and "7/2025" not in state(tmp)["done"]
    assert state(tmp)["failed"]["7/2025"]["why"].startswith("invalid")
    assert not (tmp / "awards_ext" / "ocdr_7_2025.jsonl").exists()


def test_mixed_valid_and_invalid_keeps_last_good(env):
    answers, calls, tmp = env
    out = tmp / "awards_ext"; out.mkdir()
    (out / "ocdr_7_2025.jsonl").write_text('{"good": 1}\n')
    (tmp / "ocdr_state.json").write_text(json.dumps({"pubs": [{"id": "7", "title": "Kenya: test", "iso": "KEN", "years": [2025]}],
                                                    "listed": "2999-01-01", "done": {}}))
    body = json.dumps(REL) + "\n" + '{"awards": [oops\n' * 3
    answers.append(Resp(200, _raw_gz(body)))
    _, st = ocdr.fetch()
    assert st["invalid"] == 1 and "7/2025" not in state(tmp)["done"]
    assert (out / "ocdr_7_2025.jsonl").read_text() == '{"good": 1}\n'


def test_valid_file_without_awards_is_done_empty(env):
    answers, calls, tmp = env
    answers.append(Resp(200, _gz([{"ocid": "x-2", "tender": {"id": "t"}}])))
    _, st = ocdr.fetch()
    assert st["files"] == 1 and st["invalid"] == 0 and "7/2025" in state(tmp)["done"]
    assert (tmp / "awards_ext" / "ocdr_7_2025.jsonl").read_text() == ""
