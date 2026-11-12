"""Check-now worker, pure parts (no network): python3 tests/test_check_now.py"""
from datetime import datetime, timezone

import tempfile
from pathlib import Path

from leads.check_now import clean_site, item_for, lookup_universe, pick_new, row_for_sheet
from leads.company_check import SHEET_HEAD

NOW = datetime(2026, 11, 12, 12, 30, tzinfo=timezone.utc)
ROWS = [
    ["2026-11-10T09:00:00.000Z", "Old Co", "DEU", "a@x.com"],
    ["2026-11-12T12:20:00.000Z", "Siemens Energy", "DEU", "a@x.com", "https://www.siemens-energy.com", "Energy"],
    ["2026-11-12T12:21:00.000Z", "siemens energy", "deu", "b@x.com"],              # same company again: once
    ["2026-11-12T12:22:00.000Z", "Acme", "ISR", "b@x.com", "javascript:alert(1)"],  # bad website dropped
    ["not a time", "Broken", "", ""],
]


def test_clean_site():
    assert clean_site("https://acme.com/about") == "https://acme.com/about"
    assert clean_site("acme.co.il") == "http://acme.co.il"
    assert clean_site(" www.acme.com  other ") == "http://www.acme.com"
    for bad in ("javascript:alert(1)", "ftp://acme.com", "http://localhost", "acme", "", None, "http://a b.com"):
        assert clean_site(bad) == "", bad


def test_first_pass_takes_recent_only():
    new, st = pick_new(ROWS, {}, NOW)
    assert [(n[1], n[2], n[3]) for n in new] == [("Siemens Energy", "DEU", "https://www.siemens-energy.com"), ("Acme", "ISR", "")], new
    assert new[0][4] == "Energy" and new[0][0] == 1
    assert st["rows"] == 5 and st["last"].startswith("2026-11-12T12:22")


def test_next_pass_only_new_rows():
    _, st = pick_new(ROWS, {}, NOW)
    assert pick_new(ROWS, st, NOW)[0] == []
    more = ROWS + [["2026-11-12T12:29:30.000Z", "Vestas", "DNK", "c@x.com", "vestas.com"]]
    new, st2 = pick_new(more, st, NOW)
    assert [(n[1], n[3]) for n in new] == [("Vestas", "http://vestas.com")] and st2["rows"] == 6
    # the tab became shorter (rows removed): only rows newer than the last one seen
    new, _ = pick_new(more[3:], st2, NOW)
    assert new == [], new
    newer = more[3:] + [["2026-11-12T12:29:50.000Z", "Orsted", "DNK", "c@x.com"]]
    new, _ = pick_new(newer, st2, NOW)
    assert [n[1] for n in new] == ["Orsted"], new


def test_old_requests_left_to_the_hourly_job():
    st = {"rows": 0, "last": "2026-11-01T00:00:00+00:00"}
    new, st2 = pick_new(ROWS, st, NOW)
    assert "Old Co" not in [n[1] for n in new] and st2["rows"] == 5


def test_item_for_uses_request_then_universe():
    uni = ({"Acme|ISR": ("acme.co.il", "Water & wastewater")}, {"acme": [("ISR", "acme.co.il", "Water & wastewater")]})
    req = (3, "Acme", "ISR", "", "", "t")
    assert item_for(req, uni) == ("Acme|ISR", "Acme", "ISR", "acme.co.il", "Water & wastewater", "asked in the panel (check now)")
    assert item_for((3, "Acme", "ISR", "https://acme.com", "", "t"), uni)[3] == "https://acme.com"
    assert item_for((3, "acme", "", "", "", "t"), uni)[3] == "acme.co.il"          # by name when the country is missing
    assert item_for((3, "Nobody", "FRA", "", "", "t"), ({}, {}))[3] == ""            # discovery inside check_one


def test_lookup_universe_streams_only_the_named():
    d = Path(tempfile.mkdtemp()) / "universe.csv"
    d.write_text("supplier,country,website,email,main_sector\n"
                 "Acme,ISR,acme.co.il,,Water & wastewater\n"
                 "Acme Holdings,ISR,acmeh.com,,Finance\n"
                 "Beta,DEU,,sales@beta.de,Energy\n"
                 "Gamma,FRA,,me@gmail.com,\n"
                 '"Other, with Acme in it",USA,o.com,,\n', encoding="utf-8")
    bk, bn = lookup_universe(["acme", "Beta", "Gamma"], d)
    assert bk == {"Acme|ISR": ("acme.co.il", "Water & wastewater"), "Beta|DEU": ("beta.de", "Energy"), "Gamma|FRA": ("", "")}, bk
    assert set(bn) == {"acme", "beta", "gamma"}
    assert lookup_universe([], d) == ({}, {}) and lookup_universe(["acme"], d.parent / "none.csv") == ({}, {})


def test_row_matches_push_sheet_format():
    res = {"key": "Acme|ISR", "supplier": "Acme", "country": "ISR", "checked": "2026-11-12", "checked_at": "2026-11-12T12:30:41Z",
           "verdict": "ok", "emails": [{"email": "sales@acme.com", "kind": "generic"}], "roles": [{"role": "manufacturer", "phrase": "our factory"}]}
    row = row_for_sheet(res)
    assert len(row) == len(SHEET_HEAD) == 38
    assert row[3] == "2026-11-12T12:30:41Z" and row[4] == "ok" and row[18] == "sales@acme.com (generic)" and row[13] == "manufacturer: our factory"


if __name__ == "__main__":
    for f in [test_clean_site, test_first_pass_takes_recent_only, test_next_pass_only_new_rows, test_old_requests_left_to_the_hourly_job,
              test_item_for_uses_request_then_universe, test_lookup_universe_streams_only_the_named, test_row_matches_push_sheet_format]:
        f()
    print("check now: all checks passed")
