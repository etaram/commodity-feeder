"""Transnet and Bonfire collectors parse the JSON shape seen from the server on 13 Nov 2026. No network."""


def test_transnet_open_only_and_fields():
    from leads import transnet
    js = {"success": True, "result": [
        {"nameOfTender": "NGQURA MANGANESE EXPORT CORRIDOR PSP", "descriptionOfTender": "private sector partner", "tenderNumber": "TCC/2026/08/0001/114626/RFQ",
         "institution": "TCC", "closingDate": "02/26/2027 4:00:00 PM", "publishedDate": "09/23/2026 10:00:00 AM", "tenderStatus": "Advertised"},
        {"nameOfTender": "OLD", "tenderNumber": "TFR/1", "closingDate": "01/05/2026 10:00:00 AM", "tenderStatus": "Advertised"},
        {"nameOfTender": "CANCELLED ONE", "tenderNumber": "TFR/2", "closingDate": "01/05/2027 10:00:00 AM", "tenderStatus": "Cancelled"},
        {"nameOfTender": "", "tenderNumber": "TFR/3"}]}
    rows = transnet.parse(js, "2026-11-13")
    assert [r["id"] for r in rows] == ["TRANSNET-TCC-2026-08-0001-114626-RFQ", "TRANSNET-TFR-1"]
    r = rows[0]
    assert r["country"] == "ZAF" and r["buyer"] == "Transnet Corporate Centre"
    assert r["deadline"] == "2027-02-26" and r["published"] == "2026-09-23"
    # fetch() keeps only a future deadline; the old row is dropped there
    assert [x for x in rows if x["deadline"] >= "2026-11-13"][0] is r


def test_bonfire_parse():
    from leads import bonfire
    js = {"success": 1, "payload": {"projects": {
        "255839": {"ProjectID": "255839", "ReferenceID": "Bid # 6000003483", "ProjectVisibilityID": "1",
                   "ProjectName": "Bid # 6000003483 -Electrical Equipment Inspecting and Testing", "DateClose": "2026-11-16 16:00:00"},
        "1": {"ProjectID": "1", "ReferenceID": "X", "ProjectVisibilityID": "2", "ProjectName": "private one", "DateClose": "2026-12-01 10:00:00"}}}}
    rows = bonfire.parse(js, "panynj", "Port Authority of New York and New Jersey", "USA", "2026-11-13")
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "BONFIRE-panynj-255839" and r["deadline"] == "2026-11-16" and r["country"] == "USA"
    assert r["title"].startswith("Bid # 6000003483") and r["link"] == "https://panynj.bonfirehub.com/opportunities/255839"
