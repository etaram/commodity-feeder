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


def test_eskom_rules():
    from leads import eskom
    js = [{"TENDER_ID": 96416, "REFERENCE": "E3621DXKZNOU", "HEADER_DESC": "RFI to design, manufacture and install 88kV-132kV GIS switchgear",
           "DESCRIPTION": "DISTRIBUTION", "CLOSING_DATE": "2026-11-30T10:00:00", "PUBLISHEDDATE": "2026-09-30T09:00:00", "PUBLISH": "Y",
           "Audience": "All Suppliers", "EMAIL": "someone@eskom.co.za", "E_TENDERING": True},
          {"TENDER_ID": 2, "REFERENCE": "MWP2457DXCancellatio", "HEADER_DESC": "Supply of gases. Cancellation", "CLOSING_DATE": "2027-05-28T10:00:00",
           "PUBLISHEDDATE": "2026-10-28T09:37:08", "PUBLISH": "Y"},
          {"TENDER_ID": 3, "REFERENCE": "OLD", "HEADER_DESC": "Cleaning services 48 months", "CLOSING_DATE": "2027-02-22T13:33:00",
           "PUBLISHEDDATE": "2023-05-22T13:35:12", "PUBLISH": "Y"},
          {"TENDER_ID": 4, "REFERENCE": "R", "HEADER_DESC": "Regret letter smart meters", "CLOSING_DATE": "2027-10-22T10:00:00",
           "PUBLISHEDDATE": "2026-10-22T10:00:00", "PUBLISH": "Y"}]
    rows = eskom.parse(js, "2026-11-13")
    assert [r["id"] for r in rows] == ["ESKOM-96416"]
    r = rows[0]
    assert r["deadline"] == "2026-11-30" and r["country"] == "ZAF" and r["buyer"] == "Eskom Holdings SOC Ltd - Distribution"
    assert "eskom.co.za" not in r["contact"] and "e-tendering" in r["notice_type"]
