"""leads/gebiz_awards.py: saved data.gov.sg records (2026-11-12 response) become award rows. No network."""
from leads import gebiz_awards as G

RECS = [
    {"_id": 2, "tender_no": "ACR000ETT21000003", "tender_description": "SUPPLY, DELIVERY, INSTALLATION, TESTING, COMMISSIONING OF A FULLY OPERATIONAL BUSINESS REGISTRY & REGULATORY SYSTEM WITH AN OPTION FOR MAINTENANCE",
     "agency": "Accounting And Corporate Regulatory Authority", "award_date": "14/4/2022", "tender_detail_status": "Awarded to Suppliers",
     "supplier_name": "ACCENTURE SG SERVICES PTE. LTD.", "awarded_amt": "108555723"},
    {"_id": 9, "tender_no": "X1", "tender_description": "Cancelled", "agency": "PUB", "award_date": "1/2/2023",
     "tender_detail_status": "Awarded to No Suppliers", "supplier_name": "Unknown", "awarded_amt": "0"},
]


def test_rows():
    a = G.to_row(RECS[0], "2026-11-12")
    assert a["published"] == "2022-04-14" and a["winners"] == ["ACCENTURE SG SERVICES PTE. LTD."] and a["winner_country"] == "SGP"
    assert a["value"] == 108555723.0 and a["currency"] == "SGD" and a["country"] == "SGP" and a["fetched"] == "2026-11-12"
    assert a["source_url"].startswith("https://data.gov.sg/")
    assert G.to_row(RECS[1], "2026-11-12") is None
