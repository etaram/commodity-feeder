"""Checks for tools/restore_sheets.py with a fake Sheets transport (no network, no real spreadsheet)."""
import json
import re
from urllib.parse import unquote

from tools import backup_sheets as B
from tools import restore_sheets as T
from tests.test_backup_sheets import Fake as Source, table, tabs

TARGET = "TARGET-SPREADSHEET-ID-0001"
LIVE = {"LIVE-ENGINE-SPREADSHEET-ID", "LIVE-UNIVERSE-SPREADSHEET-ID", "LIVE-STATE-SPREADSHEET-ID"}


class Transport:
    """A spreadsheet in memory behind the four HTTP calls the restore makes. It answers like the Sheets API: the
    asked window only, empty cells at the end of a row and empty rows at the end of an answer dropped."""
    def __init__(self, existing=None, fail=(), floats=False):
        self.tabs = {t: {"id": i + 1, "rows": max(len(r), 1000), "cols": 26, "cells": [list(x) for x in r]}
                     for i, (t, r) in enumerate((existing or {}).items())}
        self.fail, self.floats, self.calls = list(fail), floats, []   # fail: statuses answered first, one per call

    def writes(self):
        return [c for c in self.calls if c[0] in ("PUT", "POST")]

    def __call__(self, method, path, params, body):
        self.calls.append((method, unquote(path), params, body))
        if self.fail:
            return self.fail.pop(0), '{"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota text"}}'
        sid, _, rest = unquote(path).lstrip("/").partition("/")
        data = json.loads(body) if body else None
        if method == "GET" and not rest:
            return 200, json.dumps({"sheets": [{"properties": {"sheetId": t["id"], "title": n, "gridProperties": {
                "rowCount": t["rows"], "columnCount": t["cols"]}}} for n, t in self.tabs.items()]})
        if method == "POST" and sid.endswith(":batchUpdate"):
            for q in data["requests"]:
                if "addSheet" in q:
                    p = q["addSheet"]["properties"]
                    if p["title"] in self.tabs:
                        return 400, '{"error": {"status": "INVALID_ARGUMENT"}}'
                    self.tabs[p["title"]] = {"id": len(self.tabs) + 1, "rows": p["gridProperties"]["rowCount"],
                                             "cols": p["gridProperties"]["columnCount"], "cells": []}
                else:
                    p = q["updateSheetProperties"]["properties"]
                    t = next(x for x in self.tabs.values() if x["id"] == p["sheetId"])
                    t["rows"], t["cols"] = p["gridProperties"]["rowCount"], p["gridProperties"]["columnCount"]
            return 200, "{}"
        m = re.match(r"^values/'(.+)'!A(\d+)(?::[A-Z]+(\d+))?$", rest)
        t, a = self.tabs[m.group(1).replace("''", "'")], int(m.group(2))
        if method == "PUT":
            assert params == {"valueInputOption": "RAW"}
            assert a - 1 + len(data["values"]) <= t["rows"] and all(len(r) <= t["cols"] for r in data["values"])
            t["cells"] += [[] for _ in range(a - 1 - len(t["cells"]))]
            t["cells"][a - 1:a - 1 + len(data["values"])] = [list(r) for r in data["values"]]
            return 200, "{}"
        out = [list(r) for r in t["cells"][a - 1:int(m.group(3))]]
        for r in out:
            while r and r[-1] == "":
                r.pop()
        while out and not out[-1]:
            out.pop()
        if self.floats:   # the API is free to answer 5.0 for a 5
            out = [[float(c) if type(c) is int else c for c in r] for r in out]
        return 200, json.dumps({"values": out}) if out else "{}"


def make_export(d, sheets, render="UNFORMATTED_VALUE"):
    plan = [("state", "LIVE-STATE-SPREADSHEET-ID", t, render, True) for t in sheets]
    return B.export(Source({"LIVE-STATE-SPREADSHEET-ID": sheets}), plan, d, log=lambda *_: None)


def drill(d, tr, target=TARGET, **kw):
    lines, naps = [], []
    code, rep = T.run(str(d), target, T.Client(tr, pause=0, sleep=naps.append), ids=LIVE, log=lines.append, **kw)
    return code, rep, lines, naps


def test_refuses_a_live_spreadsheet(tmp_path, monkeypatch):
    make_export(tmp_path, {"Users": table(5)})
    for live in sorted(LIVE):
        tr = Transport()
        code, rep, lines, _ = drill(tmp_path, tr, target=live)
        assert code == 2 and rep is None and tr.calls == [] and "live spreadsheet" in lines[-1]
    # an id that is in no list but ends like a spreadsheet of the manifest (the state sheet when STATE_SHEET_ID is unset)
    tr = Transport()
    assert T.run(str(tmp_path), "SOME-OTHER-LONG-PREFIX-EET-ID", T.Client(tr, pause=0), ids=set(), log=lambda *_: None)[0] == 2
    assert tr.calls == []
    # the ids come from where they are defined: leads/push.py and the environment
    from leads.push import LEADS_SHEET, UNIVERSE_SHEET
    monkeypatch.setenv("STATE_SHEET_ID", "STATE-FROM-THE-ENVIRONMENT-1")
    assert T.live_ids() == {LEADS_SHEET, UNIVERSE_SHEET, "STATE-FROM-THE-ENVIRONMENT-1"}
    for live in T.live_ids():
        assert T.run(str(tmp_path), live, T.Client(tr, pause=0), log=lambda *_: None)[0] == 2
    assert T.run(str(tmp_path), "https://docs.google.com/spreadsheets/d/x", None, ids=LIVE, log=lambda *_: None)[0] == 2
    assert tr.calls == [] and not (tmp_path / T.REPORT).exists()


def test_refuses_when_the_target_tab_has_data(tmp_path):
    make_export(tmp_path, {"Users": table(5), "Locks": table(3)})
    tr = Transport(existing={"Locks": [[], ["", "something"]]})
    code, rep, lines, _ = drill(tmp_path, tr)
    assert code == 2 and rep is None and "already has data" in lines[-1] and "Locks" in lines[-1]
    assert tr.writes() == [] and "Users" not in tr.tabs            # refused before the first write, for every tab
    # a same-named tab that is empty is filled; a tab with data that is not restored is left alone
    tr = Transport(existing={"Locks": [], "Sheet1": [["keep", "me"]], "Small": []})
    tr.tabs["Locks"].update(rows=1, cols=1)
    code, rep, _, _ = drill(tmp_path, tr)
    assert code == 0 and tr.tabs["Locks"]["cells"] == table(3) and tr.tabs["Sheet1"]["cells"] == [["keep", "me"]]


def test_refuses_a_damaged_export(tmp_path):
    man = make_export(tmp_path, {"Users": table(30)})
    f = tmp_path / man["tabs"][0]["file"]
    f.write_bytes(f.read_bytes().replace(b"row 7", b"row X"))
    tr = Transport()
    code, _, lines, _ = drill(tmp_path, tr)
    assert code == 2 and tr.calls == [] and "failed the check" in lines[-1]


def test_batching_by_rows_and_by_bytes(tmp_path):
    make_export(tmp_path, {"Activity": table(25000)})
    tr = Transport()
    code, rep, _, _ = drill(tmp_path, tr)
    puts = [json.loads(c[3])["values"] for c in tr.calls if c[0] == "PUT"]
    assert code == 0 and [len(p) for p in puts] == [10000, 10000, 5000] and rep["tabs"][0]["write_requests"] == 3
    assert [c[1].split("!")[1] for c in tr.calls if c[0] == "PUT"] == ["A1", "A10001", "A20001"]
    assert tr.tabs["Activity"]["cells"] == table(25000)
    # long cells: the size of the request body decides, measured in the bytes that are sent (Hebrew is 2 bytes a letter)
    rows = [[i, "ש" * 20000] for i in range(200)]
    parts = T.batches(rows)
    assert len(parts) > 3 and [r for _, p in parts for r in p] == rows
    assert [s for s, _ in parts] == [1 + sum(len(p) for _, p in parts[:i]) for i in range(len(parts))]
    assert all(len(json.dumps(p, ensure_ascii=False).encode()) <= T.MAX_BYTES + 100 for _, p in parts)
    assert [len(p) for _, p in T.batches([["x" * 50], ["y" * 50]], max_bytes=10)] == [1, 1]   # a row over the limit goes alone


def test_retry_on_429_and_5xx(tmp_path):
    make_export(tmp_path, {"Users": table(5)})
    tr = Transport(fail=[429, 503, 429])
    code, rep, _, naps = drill(tmp_path, tr)
    assert code == 0 and rep["totals"]["matched"] == 1 and naps == [2, 4, 8]      # the pause grows
    tr = Transport(fail=[429] * 50)                                              # it does not retry for ever
    code, _, lines, naps = drill(tmp_path, tr)
    assert code == 2 and len(tr.calls) == 6 and "could not be read" in lines[-1] and "quota text" not in lines[-1]
    make_export(tmp_path, {"Users": table(5), "Locks": table(4)})
    flaky = Transport()

    def send(*a):                                # every write to Users is rejected (not a retryable status)
        if a[0] == "PUT" and "Users" in unquote(a[1]):
            return 403, '{"error": {"status": "PERMISSION_DENIED", "message": "secret text"}}'
        return flaky(*a)
    code, rep, lines, _ = drill(tmp_path, send)
    assert code == 1 and [r["content_match"] for r in rep["tabs"]] == [False, True]   # one failed tab does not hide the others
    assert rep["tabs"][0]["error"] == "HTTP 403 PERMISSION_DENIED" and "secret text" not in "\n".join(lines)


def test_verification_fails_on_one_changed_cell(tmp_path):
    make_export(tmp_path, {"Users": table(300), "Locks": table(4)})
    tr = Transport()

    def send(method, path, params, body):        # the spreadsheet stores one cell differently from what was sent
        out = tr(method, path, params, body)
        if method == "PUT" and "Users" in unquote(path):
            tr.tabs["Users"]["cells"][122][1] = "row 122 "
        return out
    code, rep, lines, _ = drill(tmp_path, send)
    u, l = rep["tabs"]
    assert code == 1 and not u["content_match"] and l["content_match"]
    assert (u["rows_restored"], u["cols_restored"]) == (300, 3) and u["first_difference"] == {"row": 123, "col": 2}
    assert lines[0].startswith("FAIL state/Users") and "row 123, column 2" in lines[0] and "FAILED: 1 of 2" in lines[-1]
    # a number that came back as text, and a missing last row, are differences too
    for change in (lambda c: c[5].__setitem__(0, "5"), lambda c: c.pop()):
        tr = Transport()

        def send2(method, path, params, body, change=change):
            out = tr(method, path, params, body)
            if method == "PUT" and "Users" in unquote(path):
                change(tr.tabs["Users"]["cells"])
            return out
        assert drill(tmp_path, send2)[0] == 1


def test_clean_run(tmp_path):
    odd = [["id", "text", "flag", "n"], [1, "=SUM(A1:A9)", True, 2.5], [], [2, " kept as typed ", False, ""], [3, "סוד כמוס", "", None]]
    man = make_export(tmp_path, {"Users": table(40), "Owner's tab": odd, "Empty": []})
    tr = Transport(floats=True)
    code, rep, lines, _ = drill(tmp_path, tr)
    assert code == 0 and len(lines) == 4 and lines[-1].startswith("restore drill PASSED: 3 of 3 tabs match")
    assert tr.tabs["Owner's tab"]["cells"][1][1] == "=SUM(A1:A9)"                # sent as text with RAW, never as input
    assert all(c[2] == {"valueInputOption": "RAW"} for c in tr.calls if c[0] == "PUT")
    by = {r["tab"]: r for r in rep["tabs"]}
    assert set(by["Users"]) == {"tab", "source", "rows_expected", "rows_restored", "cols_expected", "cols_restored",
                                "content_match", "byte_identical", "write_requests", "seconds"}
    assert (by["Users"]["source"], by["Users"]["rows_restored"], by["Users"]["cols_restored"]) == ("state", 40, 3)
    assert (by["Empty"]["rows_restored"], by["Empty"]["content_match"]) == (0, True)
    assert not by["Users"]["byte_identical"] and by["Users"]["content_match"]     # 5.0 for 5: equal after normalising
    assert rep["totals"]["tabs"] == 3 and rep["totals"]["failed"] == 0 and rep["totals"]["rows_restored"] == 40 + 5
    assert json.loads((tmp_path / T.REPORT).read_text(encoding="utf-8")) == rep
    # neither the log nor the report holds a cell, or a whole spreadsheet id
    text = "\n".join(lines) + (tmp_path / T.REPORT).read_text(encoding="utf-8")
    assert not any(w in text for w in ("סוד", "kept as typed", "row 7", "SUM", TARGET, "LIVE-STATE-SPREADSHEET-ID"))
    # byte-identical when the API answers the same types; a second drill on the same export needs a fresh target
    again = {r["tab"]: r for r in drill(tmp_path, Transport())[1]["tabs"]}
    assert again["Users"]["byte_identical"] and not again["Owner's tab"]["byte_identical"]   # that export ends rows with empty cells
    assert drill(tmp_path, tr)[0] == 2
    assert [e["status"] for e in man["tabs"]] == ["ok"] * 3


def test_only_and_dry_run(tmp_path):
    make_export(tmp_path, {"Users": table(40), "Locks": table(4), "Outbox": table(9)})
    tr = Transport()
    code, rep, lines, _ = drill(tmp_path, tr, only=["Locks", "Outbox"])
    assert code == 0 and [r["tab"] for r in rep["tabs"]] == ["Locks", "Outbox"] and "Users" not in tr.tabs
    assert drill(tmp_path, Transport(), only=["Nope"])[0] == 2
    lines = []
    assert T.run(str(tmp_path), TARGET, None, dry_run=True, ids=LIVE, log=lines.append) == (0, None)
    assert len(lines) == 4 and "nothing was sent" in lines[-1]
    assert T.main([str(tmp_path)]) == 2 and T.main([str(tmp_path), "--target", TARGET, "--dry-run"]) == 0


def test_normalise():
    assert T.normalise([[1.0, None, "a ", "", None], [], [""], [None]]) == [[1, "", "a "]]
    assert T.normalise([[True, 0, 2.5, "5"]]) == [[True, 0, 2.5, "5"]]             # kinds are kept
    assert T.first_difference([[1, "x"]], [[1, "x"]]) is None and T.first_difference([[1]], [[True]]) == (1, 1)
    assert T.content_hash([[1, "ש"]]) == __import__("hashlib").sha256('[1,"ש"]\n'.encode()).hexdigest()
