"""Checks for tools/backup_sheets.py and tools/restore_sheets_check.py with a fake Sheets client (no network)."""
import hashlib
import json
import re
from pathlib import Path

from tools import backup_sheets as B
from tools import restore_sheets_check as R

ROOT = Path(__file__).resolve().parent.parent


class Fake:
    """Answers like the Sheets values API: the asked window only, empty rows at the end of an answer dropped."""
    def __init__(self, sheets, grid_rows=None, fail=()):
        self.sheets, self.grid_rows, self.fail, self.calls = sheets, grid_rows or {}, set(fail), []

    def grids(self, sid):
        return {t: (self.grid_rows.get(t, len(rows) + 50), max((len(r) for r in rows), default=1) + 2) for t, rows in self.sheets[sid].items()}

    def values(self, sid, rng, render):
        m = re.match(r"^'(.+)'!A(\d+):([A-Z]+)(\d+)$", rng)
        tab, a, b = m.group(1).replace("''", "'"), int(m.group(2)), int(m.group(4))
        self.calls.append((tab, a, b, render))
        if tab in self.fail:
            raise RuntimeError(f"500 backend error for {sid}")
        out = [list(r) for r in self.sheets[sid][tab][a - 1:b]]
        while out and not any(out[-1]):
            out.pop()
        return out


def table(n, cols=3):
    return [["id", "name", "note"][:cols]] + [[i, f"row {i}", "הערה"][:cols] for i in range(1, n)]


def tabs(*names, sid="SHEET-ID-STATE1", group="state"):
    return [(group, sid, t, "UNFORMATTED_VALUE", True) for t in names]


def test_paging(tmp_path):
    rows = table(2345)
    c = Fake({"SHEET-ID-STATE1": {"Activity": rows}}, {"Activity": 5000})
    man = B.export(c, tabs("Activity"), tmp_path, page=1000, log=lambda *_: None)
    e = man["tabs"][0]
    assert (e["status"], e["rows"], e["cols"]) == ("ok", 2345, 3)
    assert [json.loads(x) for x in (tmp_path / e["file"]).read_text(encoding="utf-8").splitlines()] == rows
    # three pages, then one look at the rest of the grid; never one request for the whole tab
    assert [(a, b) for _, a, b, _ in c.calls] == [(1, 1000), (1001, 2000), (2001, 3000), (3001, 5000)]


def test_paging_edges(tmp_path):
    exact = table(2000)                       # the data ends exactly on a page border
    gap = table(300) + [[]] * 1500 + [["late", "row"]]   # a hole longer than a page, then more data
    quote = table(5)
    c = Fake({"S": {"Exact": exact, "Gap": gap, "Owner's tab": quote, "Empty": []}}, {"Exact": 2000, "Gap": 4000})
    man = B.export(c, tabs("Exact", "Gap", "Owner's tab", "Empty", sid="S"), tmp_path, page=1000, log=lambda *_: None)
    by = {e["tab"]: e for e in man["tabs"]}
    assert by["Exact"]["rows"] == 2000 and by["Gap"]["rows"] == 1801 and by["Owner's tab"]["rows"] == 5
    got = [json.loads(x) for x in (tmp_path / by["Gap"]["file"]).read_text(encoding="utf-8").splitlines()]
    assert got[299] == gap[299] and got[300] == [] and got[1800] == ["late", "row"]   # rows keep their position
    assert (by["Empty"]["status"], by["Empty"]["rows"], by["Empty"]["cols"]) == ("ok", 0, 0)
    assert len({e["file"] for e in man["tabs"]}) == 4


def test_missing_tab_and_error(tmp_path):
    c = Fake({"SHEET-ID-STATE1": {"Users": table(4), "Locks": table(9)}}, fail={"Locks"})
    lines = []
    man = B.export(c, tabs("Users", "Missions", "Locks"), tmp_path, log=lines.append)
    by = {e["tab"]: e for e in man["tabs"]}
    assert by["Missions"]["status"] == "absent" and by["Missions"]["file"] == "" and by["Missions"]["rows"] == 0
    assert by["Users"]["status"] == "ok"                       # a missing tab does not stop the others
    assert by["Locks"]["status"] == "error"
    text = "\n".join(lines) + (tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert "SHEET-ID-STATE1" not in text and by["Users"]["sheet_id_suffix"] == "STATE1"   # the id suffix only
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json", "state__Users.jsonl"]


def test_manifest_hashes(tmp_path):
    c = Fake({"SHEET-ID-STATE1": {"Users": table(40), "App Log": table(7, cols=2)}})
    man = B.export(c, tabs("Users", "App Log"), tmp_path, log=lambda *_: None)
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == man
    for e in man["tabs"]:
        assert hashlib.sha256((tmp_path / e["file"]).read_bytes()).hexdigest() == e["sha256"]
        assert set(e) >= {"sheet", "sheet_id_suffix", "tab", "rows", "cols", "sha256", "exported_at", "status"}
        assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", e["exported_at"])
    assert [e["cols"] for e in man["tabs"]] == [3, 2]
    assert all(ok for ok, _ in R.check(tmp_path)) and R.main([str(tmp_path)]) == 0


def test_half_rows_guard():
    def man(**rows):
        return {"tabs": [{"sheet": "state", "tab": t, "status": "ok" if n is not None else "absent", "rows": n or 0, "guarded": t != "Pipeline"}
                         for t, n in rows.items()]}
    prev = man(Users=100, Activity=4000, Locks=10, Missions=None, Pipeline=500)
    assert B.shrunk(prev, man(Users=50, Activity=4100, Locks=10, Missions=3, Pipeline=500)) == []   # exactly half is kept
    assert B.shrunk(prev, man(Users=49, Activity=4100, Locks=10)) == ["state/Users: 100 rows before, 49 now"]
    bad = B.shrunk(prev, man(Users=100, Activity=0, Locks=None, Pipeline=1))     # wiped, and a tab that disappeared
    assert [b.split(":")[0] for b in bad] == ["state/Activity", "state/Locks"]      # Pipeline is not guarded
    assert B.shrunk(prev, man(Users=100)) != []                                    # tabs missing from the new export count as lost
    assert B.shrunk(prev, man(Users=100, Activity=0, Locks=10), allow=["Activity"]) == []
    assert B.shrunk(prev, man(), allow=["all"]) == []
    assert B.shrunk({"tabs": []}, man(Users=1)) == []                              # first run: nothing to compare


def test_guard_exit_code(tmp_path, monkeypatch):
    sid = "SHEET-ID-STATE1"
    full = {"Users": table(100)}
    monkeypatch.setenv("STATE_SHEET_ID", sid)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    monkeypatch.delenv("BACKUP_ALLOW_SHRINK", raising=False)
    monkeypatch.setattr(B, "plan", lambda *a: tabs("Users"))
    monkeypatch.setattr(B, "Client", lambda: Fake({sid: full}))
    assert B.main([str(tmp_path / "a")]) == 0
    prev = str(tmp_path / "a" / "manifest.json")
    assert B.main([str(tmp_path / "b"), prev]) == 0
    full["Users"] = table(10)                                  # the sheet was wiped
    assert B.main([str(tmp_path / "c"), prev]) == 1
    monkeypatch.setenv("BACKUP_ALLOW_SHRINK", "Users")
    assert B.main([str(tmp_path / "d"), prev]) == 0
    monkeypatch.delenv("STATE_SHEET_ID")
    monkeypatch.setenv("BACKUP_REQUIRE_STATE_SHEET", "1")
    assert B.main([str(tmp_path / "e")]) == 2


def test_restore_check_detects_tampering(tmp_path):
    c = Fake({"SHEET-ID-STATE1": {"Users": table(30), "Outbox": table(12)}})
    man = B.export(c, tabs("Users", "Outbox", "Missions"), tmp_path, log=lambda *_: None)
    assert R.main([str(tmp_path)]) == 0                        # an absent tab is not a failure
    f = tmp_path / man["tabs"][0]["file"]
    good = f.read_bytes()
    f.write_bytes(good.replace(b"row 7", b"row X"))            # one cell changed, same row count
    res = R.check(tmp_path)
    assert [ok for ok, _ in res] == [False, True, True] and "hash differs" in res[0][1] and R.main([str(tmp_path)]) == 1
    f.write_bytes(b"".join(good.splitlines(keepends=True)[:-1]))   # last row cut off
    assert not R.check(tmp_path)[0][0]
    f.unlink()
    assert "file missing" in R.check(tmp_path)[0][1]
    f.write_bytes(good)
    (tmp_path / "extra.jsonl").write_text("[]\n")              # a file nobody listed
    assert any("not in the manifest" in line for ok, line in R.check(tmp_path) if not ok)
    (tmp_path / "extra.jsonl").unlink()
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    m["tabs"][1]["rows"] += 1                                   # manifest and file disagree on the row count
    m["tabs"][1]["sha256"] = hashlib.sha256((tmp_path / m["tabs"][1]["file"]).read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert "manifest says" in R.check(tmp_path)[1][1]
    (tmp_path / "manifest.json").unlink()
    assert R.main([str(tmp_path)]) == 1


def test_tab_list_follows_the_app():
    src = (ROOT / "dealdesk" / "lib" / "sheets.ts").read_text(encoding="utf-8")
    block = src[src.index("const STATE_TABS = new Set(["):]
    block = re.sub(r"//[^\n]*", "", block[:block.index("]);")])
    assert sorted(re.findall(r'"([^"]+)"', block)) == sorted(B.STATE_TABS)   # dealdesk/lib/sheets.ts changed: update tools/backup_sheets.py
    p = B.plan("ST", "EN", "UN")
    assert len({B.file_name(g, t) for g, _, t, _, _ in p}) == len(p)          # no two tabs share a file
    assert all(sid == "ST" for g, sid, t, _, _ in p if t in B.STATE_TABS) and {g for g, *_ in p} == {"state", "engine", "universe"}
    assert all(sid == "EN" and g == "engine" for g, sid, t, _, _ in B.plan("", "EN", "UN") if t in B.STATE_TABS)   # as the app does
    assert not set(B.STATE_TABS) & set(B.ENGINE_TABS + B.INPUT_TABS)
