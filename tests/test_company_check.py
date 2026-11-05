"""Company check parsing (no network): python3 tests/test_company_check.py"""
from leads.company_check import analyse, emails_on, links, name_match, PARKED, text_of

PAGE = """<html><head><title>Acme Valves Ltd - Butterfly valves manufacturer</title>
<meta name="description" content="Acme Valves is a leading manufacturer of butterfly and gate valves for water utilities."></head>
<body><nav><a href="/products/butterfly-valves">Butterfly valves</a><a href="/about-us">About</a><a href="/contact">Contact</a>
<a href="https://other.com/products">x</a><a href="/files/cat.pdf">Catalogue</a><a href="/login">Login</a></nav>
<script>var a = "info@tracker.com";</script>
<h1>Butterfly valves DN50-DN1200</h1><p>Our factory in Haifa holds ISO 9001 and WRAS approvals. We export to Kenya, Uganda and Ethiopia.</p>
<p>sales@acmevalves.co.il dana.levi@acmevalves.co.il someone@gmail.com logo@2x.png Tel +972 4 123 4567. Company No. 512345678</p></body></html>"""


def test_analyse():
    r = analyse("ACME VALVES LTD", "Water & wastewater", [("https://www.acmevalves.co.il/", PAGE)])
    assert r["name_match"] == "high" and r["domain"] == "acmevalves.co.il"
    assert [x["role"] for x in r["roles"]] == ["manufacturer"], r["roles"]  # export wording is not trading
    assert r["export_countries"] == ["ETH", "KEN", "UGA"] and r["export_wording"]
    assert "ISO 9001" in r["certificates"] and "WRAS" in r["certificates"]
    assert {e["email"] for e in r["emails"]} == {"sales@acmevalves.co.il", "dana.levi@acmevalves.co.il"}  # own domain only
    assert {e["kind"] for e in r["emails"]} == {"generic", "named"}
    assert r["legal_ids"] == [{"kind": "Company no.", "value": "512345678"}]
    assert "Butterfly valves DN50-DN1200" in r["products"]
    assert r["sector_conflict"] is True and r["record_sector"] == "Water & wastewater"  # flagged, never overwritten here
    assert r["gaps"] == [] and r["verdict"] == "ok"


def test_mismatch_and_gaps():
    r = analyse("Totally Other Company", "", [("https://x.com/", "<title>Shop</title><p>We sell shoes</p>")])
    assert r["verdict"] == "name mismatch" and "the site does not name the company" in r["gaps"]
    assert "role not stated (maker, trader, contractor)" in r["gaps"]


def test_links_same_site_only():
    ls = links("https://www.acmevalves.co.il/", PAGE)
    assert ls[0].endswith("/about-us") and all("acmevalves.co.il" in u for u in ls)
    assert not any(u.endswith(".pdf") or "login" in u for u in ls)


def test_helpers():
    assert name_match("Grupo Fer Cons SAC", "Inicio", "nothing here")[0] == "none"
    assert PARKED.search("This domain is for sale! Buy this domain")
    assert "var a" not in text_of(PAGE)
    assert emails_on("x@sub.acme.com y@acme.com z@other.com", "acme.com") == [{"email": "x@sub.acme.com", "kind": "named"}, {"email": "y@acme.com", "kind": "named"}]


if __name__ == "__main__":
    for f in [test_analyse, test_mismatch_and_gaps, test_links_same_site_only, test_helpers]:
        f()
    print("company check: all checks passed")
