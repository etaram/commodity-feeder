from leads import filings


def test_parse_edgar_hit():
    js = {"hits": {"hits": [{"_id": "0001193125-26-123456:d123456d8k.htm",
                             "_source": {"display_names": ["Acme Mining Corp  (AMC)  (CIK 0000012345)"], "ciks": ["0000012345"],
                                         "adsh": "0001193125-26-123456", "file_date": "2026-11-10", "form": "8-K"}},
                            {"_id": "x", "_source": {"display_names": [], "ciks": []}}]}}
    rows = filings.parse(js, "buys equipment / capex", "new production line", "2026-11-13")
    assert len(rows) == 1
    r = rows[0]
    assert r["cik"] == "12345" and r["form"] == "8-K" and r["filed"] == "2026-11-10"
    assert r["link"] == "https://www.sec.gov/Archives/edgar/data/12345/000119312526123456/d123456d8k.htm"
    assert r["company"].startswith("Acme Mining Corp")
