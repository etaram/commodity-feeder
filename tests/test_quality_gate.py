from leads.quality_gate import gate

OK = {"key": "k", "supplier": "Acme Steel Ltd", "country": "KEN", "verdict": "ok", "name_match": "high",
      "roles": [{"role": "manufacturer"}], "products": ["Home", "Steel pipes", "Galvanised sheets", "Contact us"],
      "domain": "acmesteel.co.ke", "emails": [{"email": "sales@acmesteel.co.ke"}], "checked": "2026-11-12"}


def test_complete_record_passes():
    assert gate(OK)[0]


def test_each_condition_fails_alone():
    cases = {"identity": dict(OK, country="Kenya"), "site": dict(OK, verdict="unreachable"),
             "site2": dict(OK, name_match="partial"), "role": dict(OK, roles=[]),
             "products": dict(OK, products=["Home", "About us", "Contact"]),
             "contact": dict(OK, emails=[{"email": "acme@gmail.com"}], phones=[]),
             "fresh": dict(OK, checked="2025-01-01")}
    for name, rec in cases.items():
        ok, fails, _ = gate(rec)
        assert not ok and len(fails) == 1, (name, fails)


def test_phone_counts_as_official_contact():
    assert gate(dict(OK, emails=[], phones=["+254 20 123 4567"]))[0]
