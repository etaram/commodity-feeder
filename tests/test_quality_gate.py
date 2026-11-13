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


def test_chatgpt_adversarial_cases_row_152():
    """the 8 bad inputs ChatGPT showed gate 1.1 admitting must all be rejected"""
    bad = [dict(OK, country="ZZZ"), dict(OK, checked="2099-01-01"),
           dict(OK, emails=["acmesteel.co.ke"], phones=[]), dict(OK, emails=[{"email": "x@co.ke"}], phones=[]),
           dict(OK, emails=[], phones=["not-a-phone"]), dict(OK, products=["Get in touch", "Latest updates"]),
           dict(OK, roles=[{"role": "not a manufacturer"}]),
           dict(OK, roles=[], title="Acme", description="We provide software to manufacturers and factories")]
    for i, rec in enumerate(bad, 1):
        ok, fails, facts = gate(rec)
        assert not ok, (i, facts)


def test_self_description_counts():
    ok, fails, facts = gate(dict(OK, roles=[], title="Acme Steel - a leading manufacturer of steel pipes"))
    assert ok and facts["roles"] == ["manufacturer"]


def test_award_evidence_role_only_for_goods_winners():
    ok, _, facts = gate(dict(OK, roles=[], tier=1))
    assert ok and facts["roles"] == ["supplier"] and facts["role_basis"].startswith("award evidence")
    assert not gate(dict(OK, roles=[], tier=3))[0] and not gate(dict(OK, roles=[], tier=0))[0]


def test_chatgpt_row_160_failures_v14():
    """gate 1.4: the 3 new failures ChatGPT showed on gate 1.2 (row 160), with positive controls"""
    import leads.quality_gate as q
    # 1. missing country reference list fails closed
    saved = set(q.ISO_CODES)
    try:
        q.ISO_CODES.clear()
        ok, fails, _ = q.gate(dict(OK, country="ZZZ"))
        assert not ok and any("reference list" in f for f in fails)
        ok, _, _ = q.gate(OK)
        assert not ok                               # even a good record is not admitted without the reference list
    finally:
        q.ISO_CODES.update(saved)
    assert q.gate(OK)[0]
    # 2. shared hosting: another tenant's address is not an own-domain contact; the tenant's own is
    gh = dict(OK, domain="acme.github.io", phones=[])
    assert not q.gate(dict(gh, emails=[{"email": "sales@other.github.io"}]))[0]
    assert q.gate(dict(gh, emails=[{"email": "sales@acme.github.io"}]))[0]
    assert q.registrable("shop.acme.github.io") == "acme.github.io" and q.registrable("github.io") == ""
    assert q.registrable("www.acmesteel.co.ke") == "acmesteel.co.ke"
    # 3. a third party described on the page does not give this company its role
    assert not q.gate(dict(OK, roles=[], title="Acme", description="Our partner is a manufacturer of steel pipes"))[0]
    assert not q.gate(dict(OK, roles=[], title="Acme", description="Our parent company is a leading producer of cement."))[0]
    assert q.gate(dict(OK, roles=[], title="Acme", description="We are a supplier of steel pipes. Our partner is a bank."))[0]
