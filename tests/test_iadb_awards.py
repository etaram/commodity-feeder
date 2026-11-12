"""leads/iadb_awards.py: a saved record of the IDB contract awards dataset (data.iadb.org, 2026-11-12) becomes an award
row with winner, countries, value, source URL and fetch date; future dates are quarantined. No network."""
import json

from leads import common, iadb_awards as I

REC = {"_id": "2331740", "contract_id": "VEB0747", "contract_type": "Works", "project_number": "VE-L1033",
       "project_name": "Rehabilitation of Units 1 to 6 of Powerhouse I Simon Bolivar Hydroelectric", "operation_country_code": "VE",
       "operation_country_name": "VENEZUELA", "economic_sector_name": "NEW HYDROPOWER PROJECTS", "procurement_type": "International Competitive Bidding",
       "idb_amount": "474642084", "total_amount": "474642084.0", "borrower_name": "REPUBLICA BOLIVARIANA DE VENEZUELA",
       "executing_agency": "CORPORACION ELECTRICA NACIONAL", "awarded_firm_country_code": "CN", "awarded_firm_country_name": "CHINA",
       "awarded_firm_city": "DEYANG SLCHUAN", "awarded_firm_address": "", "awarded_firm_name": "DONGFANG ELECTRIC",
       "signature_date": "2014-10-14 00:00:00.000000000", "last_modification_date": "2015-09-29 09:17:15.000000000"}


def test_award_row():
    a = I.to_row(REC, "2026-11-12")
    assert a["winners"] == ["DONGFANG ELECTRIC"] and a["winner_country"] == "CHN" and a["country"] == "VEN"
    assert a["published"] == "2014-10-14" and a["value"] == 474642084.0 and a["currency"] == "USD"
    assert a["source_url"].startswith("https://data.iadb.org/") and a["fetched"] == "2026-11-12"
    assert a["buyer"] == "CORPORACION ELECTRICA NACIONAL" and a["link"].endswith("VE-L1033")
    assert I.to_row({**REC, "awarded_firm_name": ""}, "2026-11-12") is None


def test_future_dates_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "LEADS", tmp_path)
    ok, n = common.quarantine_future([{"id": "a", "published": "2014-10-14"}, {"id": "b", "published": "2999-01-01"}], "iadb_awards")
    assert [r["id"] for r in ok] == ["a"] and n == 1
    q = [json.loads(x) for x in (tmp_path / "quarantine" / "iadb_awards.jsonl").read_text().splitlines()]
    assert q[0]["id"] == "b" and q[0]["reason"] == "published in the future"
