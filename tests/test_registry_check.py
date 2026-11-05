"""Pure checks for leads/registry_check.py and the structured-data / refresh parts of leads/company_check.py (no network)."""
from leads.company_check import changes, structured_on
from leads.registry_check import judge_lei, judge_vies, name_score, norm, vat_parts


def rec(name, country="DE", status="ACTIVE", lei="529900ABCDEFGHIJKL12"):
    return {"id": lei, "attributes": {"lei": lei, "entity": {"legalName": {"name": name}, "status": status, "registeredAs": "HRB 1234",
            "legalAddress": {"addressLines": ["Hauptstr. 1"], "postalCode": "10115", "city": "Berlin", "country": country}},
            "registration": {"status": "ISSUED"}}}


def test_names():
    assert norm("Martin &amp; Servera AB") == norm("Martin and Servera") == "martin servera"
    assert name_score("SIEMENS AKTIENGESELLSCHAFT", "Siemens Aktiengesellschaft") == 1.0
    assert name_score("Controlware GmbH", "CONTROLWARE GMBH") == 1.0
    assert name_score("Acme Valves Ltd", "Acme Pumps Ltd") < 0.75


def test_lei_verdicts():
    assert judge_lei("Controlware GmbH", "DEU", rec("Controlware GmbH"))["verdict"] == "verified"
    v = judge_lei("Controlware GmbH", "DEU", rec("Controlware GmbH"))
    assert v["evidence"].endswith("529900ABCDEFGHIJKL12") and v["register_address"].startswith("Hauptstr. 1")
    assert judge_lei("Controlware GmbH", "AUT", rec("Controlware GmbH"))["verdict"] == "not found"  # another country: not this company
    assert judge_lei("Controlware GmbH", "DEU", rec("Controlware GmbH", status="INACTIVE"))["verdict"] == "conflict"
    assert judge_lei("Controlware Systems GmbH", "DEU", rec("Controlware GmbH"))["verdict"] in ("likely", "not found")


def test_vat():
    assert vat_parts("DE 811 152 011", "DEU") == ("DE", "811152011")
    assert vat_parts("811152011", "DEU") == ("DE", "811152011")
    assert vat_parts("FR12345678901", "DEU") is None  # another country's prefix
    assert vat_parts("EL094014201", "GRC") == ("EL", "094014201")
    assert vat_parts("DE811152011", "USA") is None
    assert judge_vies("Acme GmbH", {"isValid": True, "name": "---"})["vat_verdict"].startswith("valid")
    assert judge_vies("Acme GmbH", {"isValid": True, "name": "ACME GMBH"})["vat_verdict"] == "verified"
    assert judge_vies("Acme GmbH", {"isValid": True, "name": "Other Trading SRL"})["vat_verdict"] == "conflict"
    assert judge_vies("Acme GmbH", {"isValid": False})["vat_verdict"] == "invalid"
    assert judge_vies("Acme GmbH", None)["vat_verdict"] == "unavailable"


def test_structured_data():
    page = '''<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"Acme Valves",
    "legalName":"Acme Valves GmbH","vatID":"DE811152011","telephone":"+49 30 1234","sameAs":["https://www.linkedin.com/company/acme-valves"],
    "address":{"@type":"PostalAddress","streetAddress":"Hauptstr. 1","postalCode":"10115","addressLocality":"Berlin","addressCountry":"DE"}},
    {"@type":"Product","name":"Butterfly valves DN50-DN1200"},{"@type":"Product","name":"Our Business"}]}</script>'''
    org, prods = structured_on([page])
    assert org["legal_name"] == "Acme Valves GmbH" and org["vat"] == "DE811152011" and "Berlin" in org["address"]
    assert prods == ["Butterfly valves DN50-DN1200"]  # menu words are not products, even in structured data


def test_changes():
    prev = {"emails": [{"email": "sales@acme.com"}], "phones": ["+49 30 1"], "website": "https://acme.com/", "products": ["a", "b", "c"]}
    cur = {"emails": [{"email": "info@acme.com"}], "phones": ["+49 30 1"], "domain": "acme-valves.com", "products": ["x", "y", "z"]}
    c = changes(prev, cur)
    assert any("e-mails removed: sales@acme.com" in x for x in c) and any("website moved" in x for x in c) and any("products changed" in x for x in c)
    assert changes(prev, {**prev, "domain": "acme.com"}) == []


if __name__ == "__main__":
    for f in [test_names, test_lei_verdicts, test_vat, test_structured_data, test_changes]:
        f()
    print("registry check: all checks passed")
