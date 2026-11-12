"""leads/source_cycle.py: sealing round trip, robots and page classification, weekly report from saved snapshots (no network)."""
import json

from leads import common, source_cycle as sc


def _keys(tmp_path):
    from cryptography.hazmat.primitives import serialization as s
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = tmp_path / "pub.pem"
    pub.write_bytes(k.public_key().public_bytes(s.Encoding.PEM, s.PublicFormat.SubjectPublicKeyInfo))
    return pub, k.private_bytes(s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption())


def test_seal_round_trip(tmp_path):
    pub, priv = _keys(tmp_path)
    blob = sc.seal("Lagos tender page é".encode(), pub)
    assert b"Lagos" not in blob
    assert sc.unseal(blob, priv).decode() == "Lagos tender page é"


def test_robots_and_page_classes():
    rob = "User-agent: *\nDisallow: /admin\n\nUser-agent: SinderSources\nDisallow: /tenders/private\n"
    assert sc.robots_allows(rob, "https://x.gov/tenders/list") == "allowed"
    assert sc.robots_allows(rob, "https://x.gov/tenders/private/1") == "disallowed"
    assert sc.classify_page(403, "<html><title>Just a moment...</title></html>") == "challenge"
    assert sc.classify_page(200, "<form><input type='password' name='p'></form>") == "login"
    assert sc.classify_page(200, "<table>" + "<tr><td>Tender 1</td></tr>" * 400 + "</table>") == "open"
    assert sc.classify_page(0, "") == "unreachable"


def test_weekly_report_counts_and_change(tmp_path, monkeypatch):
    part, aw, reg = tmp_path / "partial", tmp_path / "awards", tmp_path / "registry"
    part.mkdir(); (aw / "gebiz").mkdir(parents=True)
    (part / "kenya.json").write_text(json.dumps({"rows": [{"country": "KEN", "deadline": "2999-01-01"}, {"country": "KEN", "deadline": "2000-01-01"}]}))
    (part / "etimad.json").write_text(json.dumps({"rows": [{"country": "SAU", "deadline": ""}]}))
    import datetime as dt
    day = str(dt.date.today())
    (aw / "gebiz" / f"{day}.json").write_text(json.dumps([{"id": "1", "winner": "A Pte Ltd", "country": "SGP"}, {"id": "e", "empty": True}]))
    monkeypatch.setattr(sc, "PARTIAL", part); monkeypatch.setattr(common, "AWARDS", aw)
    monkeypatch.setattr(sc, "REG", reg); monkeypatch.setattr(sc, "REPORT", reg / "r.json"); monkeypatch.setattr(sc, "HISTORY", reg / "h.json")
    monkeypatch.setattr(sc, "CANDIDATES", reg / "none.csv"); monkeypatch.setattr(sc, "PRIVATE", tmp_path / "noprivate")
    monkeypatch.setattr(sc, "LEADS", tmp_path)
    reg.mkdir()
    (reg / "h.json").write_text(json.dumps([{"week": "2000-W01", "regions": {"Sub-Saharan Africa": {"open_notices": 5}}}]))
    rep = sc.report()
    assert rep["regions"]["Sub-Saharan Africa"]["open_notices"] == 1
    assert rep["regions"]["Middle East & North Africa"]["open_notices"] == 1
    assert rep["regions"]["Southeast Asia"]["awards_with_winner_12m"] == 1
    assert rep["change_vs_previous_week"]["Sub-Saharan Africa"]["open_notices"] == -4
    assert rep["regions"]["Southeast Asia"]["suppliers"] is None
