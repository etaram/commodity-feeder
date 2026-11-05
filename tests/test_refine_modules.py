"""Pure checks for leads/refine_modules.py (no network)."""
from datetime import date

from leads.refine_modules import (country_fix, dup_groups, link_verdict, refine_buyer, refine_project, refine_provider, refine_tender)

T = date(2026, 11, 5)


def tender(**k):
    r = {"id": "T1", "country": "KEN", "deadline": "2026-12-01", "published": "2026-11-01", "est_value_usd": "250000", "stage": "tender",
         "link": "https://tenders.go.ke/notice/1", "contact": "", "title_en": "Supply of water pumps", "sector": "Water & wastewater", "buyer": "Kenya Power"}
    r.update(k)
    return r


def test_tender_rules():
    r = refine_tender(tender(deadline="2026-10-01"), T, {}, {})
    assert r["status"] == "closed (deadline passed)"
    r = refine_tender(tender(published="2026-12-05"), T, {}, {})
    assert any("after its deadline" in c for c in r["conflicts"])
    r = refine_tender(tender(est_value_usd="-5"), T, {}, {})
    assert "est_value_usd" in r["cleaned"] and "no estimated value" in r["gaps"]
    r = refine_tender(tender(contact="procurement@kplc.co.ke +254 20 3201000"), T, {}, {})
    assert r["filled"]["contact_email"]["value"] == "procurement@kplc.co.ke" and r["contact_found"]
    assert r["filled"]["contact_email"]["source"] == "https://tenders.go.ke/notice/1"  # the notice is the evidence
    bf = {"email": {"value": "tenders@kplc.co.ke", "source": "https://x/notice/9"}}
    r = refine_tender(tender(), T, {}, bf)
    assert r["filled"]["contact_email"]["basis"].startswith("the buyer's own address")
    r = refine_tender(tender(), T, {"https://tenders.go.ke/notice/1": {"status": 404, "checked": "2026-11-05"}}, {})
    assert any("returns 404" in c for c in r["conflicts"])
    r = refine_tender(tender(deadline="05/12/2026"), T, {}, {})
    assert r["cleaned"]["deadline"]["to"] == "2026-12-05"


def test_countries():
    for c, want in (("KE", "KEN"), ("Kenya", "KEN"), ("Congo, Democratic Republic of", "COD"), ("KEN", "KEN")):
        assert country_fix(c, {}) == want, c
    cl = {}
    assert country_fix("Western and Central Africa", cl) == "" and cl == {}  # a region is valid for a regional project
    cl = {}
    country_fix("ZZZ", cl)
    assert cl["country"]["to"] == ""


def test_duplicates_point_to_canonical():
    rows = [tender(id="A", link="https://x.org/n/1"), tender(id="B", link="https://x.org/n/1/"), tender(id="C", link="https://x.org/n/2", title_en="Other")]
    g = dup_groups(rows, lambda r: r["id"], lambda r: [("same notice link", r["link"].rstrip("/"))], lambda r: r["id"])
    assert set(g) == {"A", "B"} and g["A"][0] == g["B"][0] and "C" not in g
    many = [tender(id=str(i), link="https://portal/x") for i in range(40)]  # a shared portal link is not an identity
    assert dup_groups(many, lambda r: r["id"], lambda r: [("same notice link", r["link"])], lambda r: r["id"]) == {}


def test_buyer_contacts_and_site():
    b = {"buyer": "Kenya Power &amp; Lighting", "country": "KEN", "buyer_email": "", "last_notice": "https://x/1"}
    r = refine_buyer(b, "k", T, [("supplychain@kplc.co.ke", "https://x/2")], None, None)
    assert r["cleaned"]["name"]["to"] == "Kenya Power & Lighting"
    assert r["filled"]["email"]["source"] == "https://x/2" and r["filled"]["website"]["value"] == "https://kplc.co.ke/"
    r = refine_buyer({**b, "buyer_email": "someone@gmail.com"}, "k", T, [], None, None)
    assert "website" not in r["filled"] and any("personal mailbox" in n for n in r["notes"])
    reg = {"verdict": "conflict", "why": "the register shows the entity as INACTIVE"}
    r = refine_buyer(b, "k", T, [], None, reg)
    assert "identity" not in r["filled"] and r["conflicts"]


def test_projects():
    p = {"project_key": "WB:P1", "project_country": "KEN", "value_usd": "100000000", "status": "closed", "open_tender_ids": "T1;T2", "open_tenders": "2",
         "next_deadline": "2026-10-01", "buyer": "Ministry", "link": "https://projects.worldbank.org/P1"}
    r = refine_project(p, T, {}, {"T1"})
    assert r["cleaned"]["open_tenders"]["to"] == "1" and "next_deadline" in r["cleaned"]
    assert any("still open" in c for c in r["conflicts"])


def test_providers():
    row = {"name": "Acme ECA", "country_hq": "DEU", "category": "ECA", "defence_ok": "maybe", "verified": "2026-01-01",
           "source_url": "https://acme-eca.de/products", "apply_url": "not stated", "check_note": ""}
    r = refine_provider(row, "finance", T, {}, None, None)
    assert any("defence_ok" in c for c in r["conflicts"]) and any("older than 180 days" in g for g in r["gaps"]) and "no apply_url" in r["gaps"]
    assert "apply_url" not in r["cleaned"]  # 'not stated' is a gap, not a broken address
    assert link_verdict({"status": 403, "checked": "x"}) == ""  # blocked is not dead


if __name__ == "__main__":
    for f in [test_tender_rules, test_countries, test_duplicates_point_to_canonical, test_buyer_contacts_and_site, test_projects, test_providers]:
        f()
    print("refine modules: all checks passed")
