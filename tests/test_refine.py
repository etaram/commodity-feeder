"""Refinement rules (no network): PYTHONPATH=. python3 tests/test_refine.py"""
from datetime import date
from leads.refine import duplicate_groups, name_in_domain, refine_one, site_rejection

T = date(2026, 11, 5)


def rec(**k):
    r = {"supplier": "Acme Valves Ltd", "country": "ISR", "website": "", "email": "", "phone": "", "legal_id": "", "products": "", "supplied": "",
         "tier": "1", "quality": "60", "wins": "3", "type": "works/services", "trader": "", "epc": "", "main_sector": "Water & wastewater"}
    r.update(k); r["_key"] = f"{r['supplier']}|{r['country']}"
    return r


def test_websites():
    assert site_rejection("https://defence.gov.au/x", "BAE Systems") == "government or public body"
    assert site_rejection("https://live.euronext.com/en/product", "Thales") == "stock exchange or market data"
    assert site_rejection("https://www.euronext.com/", "Euronext") == ""  # the exchange's own site
    assert site_rejection("https://linkedin.com/company/acme", "Acme") == "directory or social profile"
    assert name_in_domain("Electricidade de Moçambique", "edm.co.mz") and name_in_domain("Distilleries Company of Sri Lanka", "dcslgroup.net")
    assert name_in_domain("Internet Solutions", "is.co.za")
    r = refine_one(rec(website="http://www.souzacruz.com.br/", supplier="BAT Brasil", country="BRA"), None, None, None, {}, T)
    assert "website" not in r["cleaned"] and "website" not in r["filled"]  # kept as a candidate, not deleted, not official
    assert any("not confirmed" in g for g in r["gaps"])


def test_check_completes_with_provenance():
    ck = {"verdict": "ok", "name_match": "high", "website": "https://www.acmevalves.co.il/", "checked": "2026-11-05", "description": "Maker of butterfly valves",
          "products": ["Butterfly valves", "Gate valves"], "roles": [{"role": "manufacturer", "phrase": "our factory"}], "certificates": ["ISO 9001"],
          "emails": [{"email": "sales@acmevalves.co.il", "kind": "generic"}], "phones": ["+972 4 123 4567"], "sector_conflict": False, "content_hash": "x"}
    r = refine_one(rec(supplied="Butterfly valves DN300"), ck, None, None, {}, T)
    f = r["filled"]
    assert f["website"]["value"] == "https://acmevalves.co.il/" and "names the company" in f["website"]["basis"]
    assert f["products"]["source"].startswith("https://www.acmevalves") and f["products"]["date"] == "2026-11-05"
    assert f["role"]["value"] == "manufacturer" and f["emails_own_domain"]["value"] == "sales@acmevalves.co.il"
    assert "certificate check" in f["certificates"]["basis"]  # a site's claim is labelled as a claim
    assert r["contact_found"] and not r["conflicts"] and "role not established" not in r["gaps"]


def test_evidence_mismatch_and_identity():
    ck = {"verdict": "ok", "name_match": "high", "website": "https://acme.com/", "checked": "2026-11-05", "products": ["Shoes", "Leather bags"], "emails": [], "phones": []}
    r = refine_one(rec(supplied="Butterfly valves; gate valves"), ck, None, None, {}, T)
    assert any("share no word" in c for c in r["conflicts"])
    bad = refine_one(rec(website="https://acme.com/"), {"verdict": "name mismatch", "name_match": "none", "website": "https://acme.com/"}, None, None, {}, T)
    assert any("does not name" in c for c in bad["conflicts"]) and "website" not in bad["filled"]
    ns = refine_one(rec(hs_codes="8481"), None, None, None, {"acme valves": 3}, T)
    assert any("namesake" in c for c in ns["conflicts"])


def test_duplicates_never_delete():
    rows = [rec(supplier="M.A.R.K. Ltd"), rec(supplier="MARK Limited", quality="80"), rec(supplier="Other Co", website="https://abc.co.il/"), rec(supplier="Zeta", country="KEN"),
            rec(supplier="Baxter Polska", country="POL", email="przetargi@medtender.pl"), rec(supplier="Sarstedt", country="POL", email="biuro@medtender.pl")]
    d = duplicate_groups(rows)
    assert "Baxter Polska|POL" not in d  # a shared distributor or portal mailbox is not the same company
    assert d["M.A.R.K. Ltd|ISR"][0] == d["MARK Limited|ISR"][0] and d["M.A.R.K. Ltd|ISR"][1] == "MARK Limited|ISR"
    assert "Zeta|KEN" not in d


def test_soft_notes_not_conflicts():
    ck = {"verdict": "ok", "name_match": "high", "website": "https://baxter.com.pl/", "checked": "2026-11-05", "emails": [{"email": "info@baxter.com", "kind": "generic"}], "phones": []}
    r = refine_one(rec(supplier="Baxter Polska", country="POL", phone="+46 8 123 4567"), ck, None, None, {}, T)
    assert not r["conflicts"], r["conflicts"]  # a group mailbox for a national site is not a contradiction
    assert any("not a POL number" in n for n in r["notes"])


if __name__ == "__main__":
    for f in [test_websites, test_check_completes_with_provenance, test_evidence_mismatch_and_identity, test_duplicates_never_delete, test_soft_notes_not_conflicts]:
        f()
    print("refine: all checks passed")
