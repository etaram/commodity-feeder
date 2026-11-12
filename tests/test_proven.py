"""Award-proven suppliers: evidence text, role from the award, promotion with dedupe, and the build diff (no network)."""
from leads import proven, universe as u


def _row(**k):
    r = {"supplier": "Acme Cables Ltd", "country": "GRC", "tier": "4", "origin": "A", "proven_focus_usd": 250000, "wins": 1,
         "legal_id": "", "website": "", "email": "", "phone": "", "region": "Europe", "proven": "x", "award_role": "", "main_sector": ""}
    r.update(k)
    return r


def test_focus_award_and_evidence():
    assert u.focus_award("POWER", False) and u.focus_award("POWER", True)  # goods, and EPC works in power
    assert not u.focus_award("HEALTH", True)  # a health services contract is not a goods award
    assert not u.focus_award("BUILDING", True) and not u.focus_award("", False)
    ev = u.evidence({"id": "TED-761170-2026", "title": "Malta – High-voltage cable –  33kV triplex", "buyer": "Enemalta plc",
                     "country": "MLT", "published": "2026-03-02", "source": "TED"}, 6.4e6)
    assert ev["l"] == "https://ted.europa.eu/en/notice/-/detail/761170-2026" and ev["u"] == 6400000
    t = u.proven_text(ev)
    assert t.startswith("won: Malta – High-voltage cable – 33kV triplex (Enemalta plc, MLT, 2026-03-02, USD 6,400,000) [TED https://")
    assert proven.source_of(t) == "TED"
    assert proven.source_of("won: a [b] c (d) [World Bank; WB-1]") == "World Bank"


def test_award_role():
    assert u.award_role("Kabelwerk Eupen AG", 0, 3)[0] == "manufacturer"
    assert u.award_role("Delta Trading SA", 0, 2)[0] == "trader / distributor"
    assert u.award_role("Aktor ATE", 4, 5)[0] == "EPC / contractor"
    assert u.award_role("Aktor ATE", 0, 1, title="Supply and installation of 2 substations")[0] == "EPC / contractor"
    assert u.award_role("Delta Trading SA", 0, 2, role_read="manufacturer")[0] == "manufacturer"  # its website wins
    assert u.award_role("Omega SA", 0, 1)[0] == "supplier (role to confirm)"


def test_promote_proven_dedupe_and_persons():
    listed = _row(supplier="Acme Cables SA", tier="3", legal_id="EL-099999999", website="https://www.acme.gr")
    a = _row()  # one 250k focus award, no contact: listed as proven
    b = _row(supplier="Acme Cables S.A.", legal_id="EL099999999")  # same legal id as a listed record
    c = _row(supplier="Acme Hellas", website="http://acme.gr/en")  # same domain in the same country
    d = _row(supplier="ФЕДОРІН ОЛЕКСАНДР ОЛЕКСАНДРОВИЧ", country="UKR")  # a natural person
    e = _row(supplier="Small Co", proven_focus_usd=50000)  # below the threshold
    n = u.promote_proven([listed, a, b, c, d, e])
    assert n == {"promoted": 1, "duplicate_legal_id": 1, "duplicate_domain": 1, "person": 1, "over_cap": 0}
    assert a["tier"] == "3" and "proven by award" in a["tier_reason"] and "contact being found" in a["tier_reason"]
    assert b["tier"] == c["tier"] == d["tier"] == e["tier"] == "4"


def test_diff_and_queue_order():
    prev = {"A|GRC": "4", "B|BRA": "3"}
    rows = [_row(supplier="A", country="GRC", tier="3", proven="won: x [TED; T-1]", region="Europe"),
            _row(supplier="B", country="BRA", tier="3", proven="won: y [Brazil PNCP; P-1]"),       # listed before
            _row(supplier="C", country="KEN", tier="3", proven="won: z [World Bank; WB-1]", region="Sub-Saharan Africa"),
            _row(supplier="D", country="KEN", tier="4", proven="won: z [World Bank; WB-2]"),       # not listed
            _row(supplier="E", country="KEN", tier="3", proven="", region="Sub-Saharan Africa")]    # no award evidence
    new = proven.diff(prev, rows, "2026-11-12")
    assert [x["key"] for x in new] == ["A|GRC", "C|KEN"]
    s = proven.summarise(new, "2026-11-12")
    assert s["was_absent"] == 1 and s["was_tier_4"] == 1 and s["weak_regions"]["Sub-Saharan Africa"] == 1
    assert s["by_source"] == {"TED": 1, "World Bank": 1}
    assert [x["key"] for x in proven.queue_order(new)] == ["C|KEN", "A|GRC"]  # weak region first


def test_diff_without_snapshot_counts_rule_rows():
    rows = [_row(supplier="A", tier="3", proven="won: x [TED; T-1]", tier_reason="Qualified: proven by award (USD 250K, 1 win)"),
            _row(supplier="B", tier="3", proven="won: y [TED; T-2]", tier_reason="Qualified: $300K won, 2 wins, reachable")]
    assert [x["key"] for x in proven.diff({}, rows, "2026-11-12")] == ["A|GRC"]


def test_promote_cap_prefers_weak_regions(monkeypatch):
    monkeypatch.setattr(u, "PROVEN_MAX", 1)
    eu = _row(supplier="Big EU", proven_focus_usd=9e6)
    ke = _row(supplier="Nairobi Supplies", country="KEN", region="Sub-Saharan Africa", proven_focus_usd=2e5)
    n = u.promote_proven([eu, ke])
    assert n["promoted"] == 1 and n["over_cap"] == 1 and ke["tier"] == "3" and eu["tier"] == "4"
