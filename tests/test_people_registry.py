"""Registry people lane (leads/people_registry.py, leads/enrich_server.py): parsers keep business role information only,
the identity rule is strict, and the lane's results reach the merged export. All names here are invented."""
import json

from leads import enrich_server as es
from leads import people_registry as pr

FR = {"siren": "123456789", "nom_raison_sociale": "ACME FROMAGES", "nom_complet": "ACME FROMAGES (ACME)", "etat_administratif": "A",
      "dirigeants": [
          {"nom": "DUPONT (MARTIN)", "prenoms": "Jeanne, Marie", "annee_de_naissance": "1970", "date_de_naissance": "1970-05", "qualite": "Président",
           "nationalite": "Française", "type_dirigeant": "personne physique"},
          {"nom": "LEROUX", "prenoms": "Paul", "date_de_naissance": "1961-02", "qualite": "Commissaire aux comptes titulaire", "type_dirigeant": "personne physique"},
          {"siren": "999999999", "denomination": "HOLDING X", "qualite": "Administrateur", "type_dirigeant": "personne morale"},
          {"nom": "BERNARD", "prenoms": "Luc", "qualite": "Directeur général délégué", "type_dirigeant": "personne physique"}]}
NO_UNIT = {"organisasjonsnummer": "987654321", "navn": "NORDFISK AS", "hjemmeside": "www.nordfisk.example", "konkurs": False, "underAvvikling": False}
NO_ROLES = {"rollegrupper": [
    {"type": {"kode": "DAGL"}, "roller": [{"type": {"kode": "DAGL", "beskrivelse": "Daglig leder"}, "avregistrert": False,
                                           "person": {"fodselsdato": "1968-05-04", "navn": {"fornavn": "Kari", "etternavn": "Nordmann"}, "erDoed": False}}]},
    {"type": {"kode": "STYR"}, "roller": [
        {"type": {"kode": "LEDE", "beskrivelse": "Styrets leder"}, "person": {"fodselsdato": "1950-01-01", "navn": {"fornavn": "Ola", "mellomnavn": "Per", "etternavn": "Hansen"}}},
        {"type": {"kode": "VARA", "beskrivelse": "Varamedlem"}, "person": {"navn": {"fornavn": "Siri", "etternavn": "Vik"}}},
        {"type": {"kode": "MEDL", "beskrivelse": "Styremedlem"}, "fratraadt": True, "person": {"navn": {"fornavn": "Gone", "etternavn": "Away"}}}]},
    {"type": {"kode": "REVI"}, "roller": [{"type": {"kode": "REVI", "beskrivelse": "Revisor"}, "enhet": {"organisasjonsnummer": "111111111"}}]}]}
CZ = {"icoId": "12345678", "zaznamy": [{"primarniZaznam": True, "stavSubjektu": "AKTIVNI",
      "obchodniJmeno": [{"hodnota": "Stará firma s.r.o.", "datumVymazu": "2010-01-01"}, {"hodnota": "Pivovar Test s.r.o."}],
      "statutarniOrgany": [{"nazevOrganu": "Statutární orgán", "clenoveOrganu": [
          {"typAngazma": "STATUTARNI_ORGAN_CLEN", "nazevAngazma": "Jednatel", "clenstvi": {"funkce": {"vznikFunkce": "2019-03-01", "nazev": "jednatel"}},
           "fyzickaOsoba": {"jmeno": "Jan", "prijmeni": "NOVÁK", "datumNarozeni": "1975-01-01", "adresa": {"textovaAdresa": "Praha 1"}}},
          {"datumVymazu": "2018-01-01", "clenstvi": {"funkce": {"nazev": "jednatel"}}, "fyzickaOsoba": {"jmeno": "Old", "prijmeni": "MAN"}}]}],
      "spolecnici": [{"spolecnik": [{"osoba": {"nazevAngazma": "Společník", "fyzickaOsoba": {"jmeno": "Eva", "prijmeni": "SVOBODOVÁ", "datumNarozeni": "1980-02-02"}}}]}]}]}
BR = {"cnpj": "11222333000181", "razao_social": "CAFE TESTE LTDA", "situacao_cadastral": 2, "qsa": [
    {"nome_socio": "MARIA DA SILVA SOUZA", "qualificacao_socio": "Sócio-Administrador", "faixa_etaria": "Entre 41 a 50 anos", "cnpj_cpf_do_socio": "***123456**",
     "identificador_de_socio": 2, "data_entrada_sociedade": "2015-03-01"},
    {"nome_socio": "HOLDING CAFE SA", "qualificacao_socio": "Sócio", "cnpj_cpf_do_socio": "99888777000166", "identificador_de_socio": 1}]}
GB_PROFILE = {"company_number": "01234567", "company_name": "WIDGETS LIMITED", "company_status": "active"}
GB_OFFICERS = {"items": [
    {"name": "SMITH, John Paul", "officer_role": "director", "appointed_on": "2018-04-01", "date_of_birth": {"month": 4, "year": 1970}, "address": {"locality": "London"}},
    {"name": "JONES, Ann", "officer_role": "secretary"},
    {"name": "BROWN, Old", "officer_role": "director", "resigned_on": "2020-01-01"}]}

PRIVATE = ("birth", "naissance", "fodsels", "narozeni", "faixa", "cpf", "adresa", "address", "nationalit", "1970-05", "1968-05-04", "Praha 1")


def no_private(people):
    blob = json.dumps(people, ensure_ascii=False).lower()
    return not any(x.lower() in blob for x in PRIVATE)


def test_fr_parser_keeps_role_holders_only():
    ent, ppl = pr.parse_fr(FR, "Acme Fromages SAS")
    assert ent == {"id": "123456789", "name": "ACME FROMAGES", "active": True, "url": "https://annuaire-entreprises.data.gouv.fr/dirigeants/123456789"}
    assert [(p["name"], p["role"]) for p in ppl] == [("Jeanne Dupont", "chief executive"), ("Luc Bernard", "director / board")]
    assert no_private(ppl)
    assert ppl[0]["linkedin_search"] == "https://www.linkedin.com/search/results/people/?keywords=Jeanne%20Dupont%20Acme%20Fromages"
    assert ppl[0]["confidence"] == "official registry" and ppl[0]["source_name"].startswith("Registre national")


def test_no_parser_drops_deputies_auditors_and_former():
    ent, ppl = pr.parse_no(NO_UNIT, NO_ROLES, "Nordfisk AS")
    assert ent["active"] and ent["website"] == "www.nordfisk.example"
    assert [(p["name"], p["title"], p["role"]) for p in ppl] == [("Kari Nordmann", "Daglig leder (DAGL)", "chief executive"),
                                                                 ("Ola Per Hansen", "Styrets leder (LEDE)", "director / board")]
    assert no_private(ppl)


def test_cz_parser_current_members_and_partners():
    ent, ppl = pr.parse_cz(CZ, "Pivovar Test s.r.o.")
    assert ent["name"] == "Pivovar Test s.r.o." and ent["active"]
    assert [(p["name"], p["role"], p.get("since")) for p in ppl] == [("Jan Novák", "chief executive", "2019-03-01"), ("Eva Svobodová", "founder / owner", None)]
    assert no_private(ppl)


def test_br_parser_people_not_companies():
    ent, ppl = pr.parse_br(BR, "Cafe Teste Ltda")
    assert ent["active"] and [(p["name"], p["role"], p["since"]) for p in ppl] == [("Maria da Silva Souza", "chief executive", "2015-03-01")]
    assert no_private(ppl)


def test_gb_parser_name_order_and_no_dob():
    ent, ppl = pr.parse_gb(GB_PROFILE, GB_OFFICERS, "Widgets Ltd")
    assert ent["active"] and [(p["name"], p["role"], p["since"]) for p in ppl] == [("John Paul Smith", "director / board", "2018-04-01")]
    assert no_private(ppl)


def test_site_ids_by_country():
    assert pr.site_ids("FRA", [{"kind": "VAT", "value": "FR 40 123456789"}]) == "123456789"
    assert pr.site_ids("FRA", [{"kind": "SIRET", "value": "123 456 789 00012"}]) == "123456789"
    assert pr.site_ids("NOR", [{"kind": "Org.nr", "value": "987 654 321"}]) == "987654321"
    assert pr.site_ids("NOR", [{"kind": "VAT", "value": "NO987654321MVA"}]) == "987654321"
    assert pr.site_ids("CZE", [{"kind": "VAT", "value": "CZ12345678"}]) == "12345678"
    assert pr.site_ids("CZE", [{"kind": "VAT", "value": "CZ7501011234"}]) == ""  # a person's number, not a company
    assert pr.site_ids("BRA", [{"kind": "CNPJ", "value": "11.222.333/0001-81"}]) == "11222333000181"
    assert pr.site_ids("GBR", [{"kind": "Company no.", "value": "1234567"}]) == "01234567"
    assert pr.site_ids("DEU", [{"kind": "VAT", "value": "DE123456789"}]) == ""


def test_site_legal_id_patterns():
    from leads import company_check as cc
    txt = "ACME SAS - RCS Lyon B 123 456 789 - SIRET 123 456 789 00012. Org.nr. 987 654 321. IČO: 12345678. Registered in England and Wales No. 01234567"
    ids = {(k, rx.search(txt).group(1)) for k, rx in cc.LEGAL_ID if rx.search(txt)}
    assert ("RCS", "123 456 789") in ids and ("SIRET", "123 456 789 00012") in ids and ("Org.nr", "987 654 321") in ids
    assert ("ICO", "12345678") in ids and ("Company no.", "01234567") in ids


def test_identity_rule_is_strict():
    c = [("1", "ACME FROMAGES SAS", True), ("2", "ACME FROMAGES DU SUD", True), ("3", "ACME FROMAGES", False)]
    assert pr.pick("Acme Fromages", c) == ("1", "exact name")
    assert pr.pick("Acme Fromages", c + [("4", "Acme Fromages SARL", True)]) == (None, "ambiguous")
    assert pr.pick("Abc", [("5", "ABC", True)]) == (None, "no match")  # under 4 characters after suffixes
    assert pr.pick("Acme Cheese", c) == (None, "no match")


def test_role_buckets():
    assert pr.role_of("Wiceprezes zarządu") == "director / board"
    assert pr.role_of("Prezes zarządu") == "chief executive"
    assert pr.role_of("Gérant") == "chief executive"
    assert pr.role_of("Membre du conseil de surveillance") == ""
    assert pr.role_of("Varamedlem (VARA)") == ""
    assert pr.role_of("Innehaver (INNH)") == "founder / owner"


def test_lookup_by_site_id_without_name_search():
    calls = []

    class R:
        status_code = 200

        def __init__(self, js):
            self._js = js

        def json(self):
            return self._js

    class S:
        def get(self, url, **kw):
            calls.append((url, kw.get("params")))
            return R({"results": [FR]})

    class Rate:
        def wait(self):
            pass
    it = {"key": "Acme Fromages|FRA", "name": "Acme Fromages", "country": "FRA"}
    site = {"verdict": "ok", "name_match": "high", "legal_ids": [{"kind": "VAT", "value": "FR40123456789"}]}
    rec = pr.lookup(S(), "fr", it, site, Rate())
    assert rec["match"] == "registration id on the company's own site" and rec["entity"]["name_check"] == "same name"
    assert calls[0][1]["q"] == "123456789" and len(rec["people"]) == 2
    # a site that does not name the company: its id is not trusted, the name is searched instead
    calls.clear()
    rec = pr.lookup(S(), "fr", it, {**site, "name_match": "none"}, Rate())
    assert calls[0][1]["q"] == "Acme Fromages" and rec["match"] == "exact name"


def test_registry_people_reach_the_export(tmp_path):
    site = {"key": "Acme Fromages|FRA", "supplier": "Acme Fromages", "country": "FRA", "verdict": "ok", "checked_at": "2026-11-12T10:00Z",
            "people": [{"name": "Jeanne Dupont", "title": "CEO", "role": "chief executive", "source": "https://acme.example/team", "confidence": "own site"}]}
    _, ppl = pr.parse_fr(FR, "Acme Fromages")
    reg = [{"key": "Acme Fromages|FRA", "checked_at": "2026-11-12T11:00Z", "source": "fr", "match": "exact name", "entity": {"id": "123456789", "name": "ACME FROMAGES", "active": True},
            "people": ppl, "supplier": "Acme Fromages", "country": "FRA"},
           {"key": "Nordfisk|NOR", "checked_at": "2026-11-12T11:00Z", "source": "no", "match": "exact name", "entity": {"id": "987654321"},
            "people": pr.parse_no(NO_UNIT, NO_ROLES, "Nordfisk")[1], "supplier": "Nordfisk", "country": "NOR"}]
    (tmp_path / "site.jsonl").write_text(json.dumps(site) + "\n", encoding="utf-8")
    (tmp_path / "registry.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reg), encoding="utf-8")
    out = {r["key"]: r for r in es.merged(tmp_path)}
    a = out["Acme Fromages|FRA"]
    assert [p["name"] for p in a["people"]] == ["Jeanne Dupont", "Luc Bernard"]
    assert a["people"][0]["confidence"] == "own site" and a["people"][0]["also"] == [pr.SOURCE_NAME["fr"]]
    assert all(p["linkedin_search"].startswith("https://www.linkedin.com/search/results/people/?keywords=") for p in a["people"])
    assert a["registry_entity"]["id"] == "123456789" and a["enriched_at"] == "2026-11-12T11:00Z"
    b = out["Nordfisk|NOR"]
    assert b["people_only"] and len(b["people"]) == 2 and "verdict" not in b
    assert es.export(tmp_path) == 2


def test_registry_lane_runs_in_order(tmp_path, monkeypatch):
    q = [{"key": f"C{i}|FRA", "name": f"Company {i}", "country": "FRA", "website": "", "tier": t, "ev": 0, "size": "mid"} for i, t in enumerate((2, 0, 1))]
    q.append({"key": "X|DEU", "name": "X", "country": "DEU", "website": "", "tier": 0, "ev": 0, "size": "mid"})
    (tmp_path / "queue.jsonl").write_text("".join(json.dumps(x) + "\n" for x in q), encoding="utf-8")
    (tmp_path / "priority.keys").write_text("C2|FRA\n", encoding="utf-8")
    seen = []

    def fake(s, src, it, site, rate):
        seen.append(it["key"])
        return {"key": it["key"], "checked_at": "t", "source": src, "match": "exact name", "entity": {"id": "1"},
                "people": [{"name": "Ann Example", "role": "chief executive"}]}
    monkeypatch.setattr(pr, "lookup", fake)
    monkeypatch.setattr(pr, "COUNTRIES", {"FRA": "fr"})
    es.run(tmp_path, workers=0, lanes=("registry",))
    assert seen == ["C2|FRA", "C1|FRA", "C0|FRA"]  # priority first, then by tier
    st = json.loads((tmp_path / "status.json").read_text())
    assert st["registry_people"]["fr"]["looked"] == 3 and st["registry_people"]["fr"]["people"] == 3


def test_merge_server_adds_register_people_without_replacing_the_check(tmp_path):
    import gzip
    from leads import company_check as cc
    cur = {"key": "A|FRA", "checked": "2026-11-12", "checked_at": "2026-11-12T12:00Z", "verdict": "ok", "version": cc.VERSION,
           "people": [{"name": "Jeanne Dupont", "title": "CEO", "confidence": "own site"}]}
    srv = [{"key": "A|FRA", "people_only": True, "people": [{"name": "Jeanne DUPONT", "title": "Président"}, {"name": "Luc Bernard", "title": "Administrateur",
            "confidence": "official registry", "source_name": "Registre"}], "registry_entity": {"id": "1"}, "enriched_at": "2026-11-12T13:00Z"},
           {"key": "B|NOR", "people_only": True, "people": [{"name": "Kari Nordmann", "title": "Daglig leder"}], "enriched_at": "t"}]
    p = tmp_path / "x.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write("".join(json.dumps(r) + "\n" for r in srv))
    checks = {"A|FRA": cur}
    assert cc.merge_server(checks, p) == 2
    assert checks["A|FRA"]["verdict"] == "ok" and [x["name"] for x in checks["A|FRA"]["people"]] == ["Jeanne Dupont", "Luc Bernard"]
    assert checks["A|FRA"]["registry_entity"] == {"id": "1"}
    assert "checked" not in checks["B|NOR"] and "people_only" not in checks["B|NOR"]  # the hourly check still reads its site
    cell = cc.profile_cells(checks["A|FRA"])[2]
    assert cell == "Jeanne Dupont (CEO, own site); Luc Bernard (Administrateur, register: Registre)"
