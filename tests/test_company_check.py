"""Company check parsing (no network): python3 tests/test_company_check.py"""
from leads.company_check import analyse, emails_on, links, name_match, PARKED, site_sector, text_of

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
    assert emails_on("j.doe@sub.acme.com pr@acme.com z@other.com xxx@acme.com", "acme.com") == [{"email": "j.doe@sub.acme.com", "kind": "named"}, {"email": "pr@acme.com", "kind": "department"}]


def test_site_sector_scored_not_first_match():
    # real pages from the first run: a first-match keyword gave Fertiglobe ICT, Lockheed ICT, STRABAG furniture
    assert site_sector("Philadelphia Solar delivers high-efficiency PV modules and reliable mounting systems", ["PV Modules", "Steel Mounting Structures"])[0] == "POWER"
    assert site_sector("The fire truck manufacturer Rosenbauer, unique firefighting technology", ["Vehicle of the month"])[0] == "TRANSPORT_EQ"
    assert site_sector("Eakin Healthcare is a UK manufacturer of respiratory products for Critical and Neonatal Care", ["Ventilator Circuits"])[0] == "HEALTH"
    assert site_sector("STRABAG ist Österreichs größtes Bauunternehmen", ["Impressum"])[0] == ""  # too few words: unclear, not a guess
    assert site_sector("a leading global security, defense and aerospace contractor", ["Air", "Land"])[0] != "MACHINERY"  # contractor is not tractor


def test_products_roles_from_real_pages():
    # headings seen on real sites in the first runs
    from leads.company_check import product_like
    keep = ["Granular Urea", "Ammonia", "Urbino electric", "Cell Culture Media", "Aceites Vegetales", "Butterfly valves DN50-DN1200"]
    drop = ["Our Business", "Investor Relations", "Impressum", "Wir bauen auf Expertise und Innovationskraft", "70%", "Newsroom",
            "Euronaval 2026: Elbit Systems to Present UUV", "Choose your country or region", "Setari Cookie-uri", "Misión"]
    assert all(product_like(t) for t in keep) and not any(product_like(t) for t in drop)
    careers = "<title>Acme Valves</title><h1>Valves</h1>"
    jobs = "<p>Training and recruitment at Acme: find a distributor of our valves near you.</p>"
    r = analyse("Acme Valves", "", [("https://acme.com/", careers), ("https://acme.com/careers/training", jobs)])
    assert r["roles"] == [], r["roles"]  # careers pages and dealer locators do not make a service firm or a trader
    big = "<p>We export to " + ", ".join(["Kenya", "Uganda", "France", "Spain"] * 1) + ".</p><select>" + "".join(f"<option>{c}</option>" for c in ["Germany", "Italy", "Brazil", "Chile"]) + "</select>"
    r2 = analyse("Acme Valves", "", [("https://acme.com/", "<title>Acme Valves</title>" + big)])
    assert set(r2["export_countries"]) == {"KEN", "UGA", "FRA", "ESP"}, r2["export_countries"]  # only the countries in the export sentence



def test_linkedin_whatsapp_links():
    from leads.company_check import social_on
    page = ('<a href="https://www.linkedin.com/company/acme-valves/">in</a><a href="https://www.linkedin.com/shareArticle?url=x">share</a>'
            '<a href="https://www.linkedin.com/in/john-doe">John</a><a href="https://wa.me/972501234567">chat</a>'
            '<a href="https://api.whatsapp.com/send?phone=+44 20 7946 0958&amp;text=hi">wa</a><a href="https://wa.me/?text=share">share</a>')
    li, wa = social_on([page])
    assert li == "https://www.linkedin.com/company/acme-valves", li
    assert wa == ["+972501234567", "+442079460958"], wa
    r = analyse("Acme Valves", "", [("https://acme.com/", "<title>Acme Valves</title>" + page)])
    assert r["linkedin"] and r["whatsapp"]


if __name__ == "__main__":
    for f in [test_analyse, test_mismatch_and_gaps, test_links_same_site_only, test_helpers, test_site_sector_scored_not_first_match, test_products_roles_from_real_pages, test_linkedin_whatsapp_links]:
        f()
    print("company check: all checks passed")
