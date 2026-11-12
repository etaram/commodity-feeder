"""leads/tender_details.py: field extraction from official machine-readable tender records (no network).

Fixtures: tests/samples/boamp_eforms_cn.json is a real eForms competition notice as the BOAMP open-data API publishes
it (organisations removed); tests/samples/ted_eforms_cn.xml is the same notice written as eForms XML, with a tender
guarantee, a clarification deadline and a lot description added so that every XML path is exercised."""
import json
from pathlib import Path

from leads import tender_details as td

S = Path(__file__).parent / "samples"
AT = "2026-11-12"


def v(f, k):
    return f[k]["v"]


def test_eforms_xml_all_fields():
    f = td.parse_eforms(td.xml_tree((S / "ted_eforms_cn.xml").read_bytes()), "https://ted.europa.eu/en/notice/1-2026/xml", AT)
    assert v(f, "lots")["count"] == 3 and v(f, "lots")["lots"][0]["value"] == "200000 EUR"
    assert v(f, "items")[0]["cpv"] == "34913200" and "120 pcs" in v(f, "items")[0]["quantity_in_text"][0]
    assert v(f, "technical_standards") == ["EN 853", "ISO 1436", "CE marking"]
    assert v(f, "bid_security")["required"] is True and "[e-mail]" in v(f, "bid_security")["terms"]  # address scrubbed
    assert "@" not in json.dumps(f)
    assert v(f, "performance_guarantee")["quoted"][0].startswith("Performance guarantee of 10%")
    assert v(f, "clarification_deadline") == "2026-11-20 12:00"
    assert v(f, "evaluation")["method"] == "best price-quality ratio"
    assert "price 55%: Prix des prestations" in v(f, "evaluation")["criteria"]
    assert v(f, "delivery")["place"] == ["Vannes Cedex, 56019, FRH04, FRA"] and v(f, "delivery")["incoterms"] == ["DAP Chambery"]
    assert v(f, "documents")[0]["url"].startswith("https://")
    assert v(f, "eligibility")[0]["type"] == "other"
    # provenance on every field
    assert all(x["s"] and x["a"] == AT and x["b"] for x in f.values())


def test_eforms_json_matches_xml_and_states_gaps():
    f = td.parse_eforms(td.json_tree(json.loads((S / "boamp_eforms_cn.json").read_text(encoding="utf-8"))), "u", AT)
    assert v(f, "lots")["count"] == 3
    assert v(f, "evaluation")["criteria"][-1] == "price 55%: Prix des prestations"
    # the real notice states no guarantee, no clarification deadline and no standard: never invented
    assert v(f, "bid_security") == td.NS and v(f, "clarification_deadline") == td.NS and v(f, "technical_standards") == td.NS
    assert v(f, "performance_guarantee") == td.NS


def test_prozorro():
    d = {"title": "Трансформатори", "awardCriteria": "lowestCost", "procurementMethodType": "aboveThresholdEU",
         "enquiryPeriod": {"endDate": "2026-11-20T00:00:00+02:00"}, "tenderPeriod": {"endDate": "2026-12-01T10:00:00+02:00"},
         "guarantee": {"amount": 50000, "currency": "UAH"},
         "items": [{"description": "Трансформатор ТМГ 400 кВА згідно ДСТУ 3463", "quantity": 4, "unit": {"name": "штука"},
                    "classification": {"id": "31170000-8"}, "deliveryAddress": {"locality": "Київ", "countryName": "Україна"},
                    "deliveryDate": {"endDate": "2027-03-01T00:00:00+02:00"}}],
         "criteria": [{"classification": {"id": "CRITERION.SELECTION.TECHNICAL_PROFESSIONAL_ABILITY.REFERENCES"},
                       "title": "Наявність документально підтвердженого досвіду виконання аналогічного договору"},
                      {"classification": {"id": "CRITERION.OTHER.CONTRACT.GUARANTEE"}, "title": "Забезпечення виконання договору",
                       "description": "5% від ціни договору"}],
         "documents": [{"url": "https://public-docs.prozorro.gov.ua/get/abc", "documentType": "technicalSpecifications", "title": "ТЗ.pdf"}]}
    f = td.parse_prozorro(d, "https://public-api.prozorro.gov.ua/api/2.5/tenders/x", AT)
    assert v(f, "items")[0]["quantity"] == "4 штука" and v(f, "items")[0]["cpv"] == "31170000-8"
    assert v(f, "bid_security") == {"required": True, "amount": "50000 UAH"}
    assert "5%" in v(f, "performance_guarantee")["terms"][0]
    assert v(f, "eligibility")[0]["type"].startswith("technical professional ability")
    assert v(f, "evaluation")["method"] == "lowest price"
    assert v(f, "clarification_deadline") == "2026-11-20"
    assert v(f, "technical_standards") == ["ДСТУ 3463"]
    assert v(f, "delivery") == {"place": ["Київ, Україна"], "deliver_by": ["2027-03-01"]}
    assert v(f, "lots") == td.NS


def test_pncp():
    compra = {"objetoCompra": "Aquisição de transformadores", "informacaoComplementar": "Prazo de entrega de 45 dias. Garantia de execução contratual de 5%.",
              "dataEncerramentoProposta": "2026-12-01T09:00:00", "modalidadeNome": "Pregão - Eletrônico", "modoDisputaNome": "Aberto",
              "unidadeOrgao": {"municipioNome": "Recife", "ufSigla": "PE"}, "linkSistemaOrigem": "https://www.gov.br/compras/x"}
    itens = [{"numeroItem": 1, "descricao": "Transformador trifásico 75 kVA conforme NBR 5356", "quantidade": 10, "unidadeMedida": "Unidade",
              "valorUnitarioEstimado": 25000.5, "criterioJulgamentoNome": "Menor preço"}]
    arqs = [{"url": "https://pncp.gov.br/pncp-api/v1/orgaos/1/compras/2026/1/arquivos/1", "tipoDocumentoNome": "Edital", "titulo": "Edital"}]
    f = td.parse_pncp(compra, itens, arqs, ("c", "i", "a"), AT)
    assert v(f, "items")[0]["quantity"] == "10 Unidade" and f["items"]["s"] == "i"
    assert v(f, "documents")[0]["type"] == "Edital" and f["documents"]["s"] == "a"
    assert v(f, "evaluation")["method"] == "Menor preço"
    assert v(f, "technical_standards") == ["NBR 5356"]
    assert v(f, "delivery")["delivery_time_quoted"] and v(f, "delivery")["buyer_unit_location"] == "Recife, PE"
    assert v(f, "eligibility") == td.NS and v(f, "clarification_deadline") == td.NS


def test_chile():
    x = {"Nombre": "Adquisición de bombas", "Descripcion": "Entrega en 30 días. Garantía de fiel cumplimiento 5%.", "Tipo": "LP",
         "Fechas": {"FechaCierre": "2026-12-03T15:00:00", "FechaFinal": "2026-11-21T15:00:00"}, "TiempoDuracionContrato": 12,
         "UnidadTiempoDuracionContrato": 4,
         "Items": {"Listado": [{"NombreProducto": "Bombas centrífugas", "Descripcion": "Bomba 50 HP", "Cantidad": 6, "UnidadMedida": "Unidad",
                                "CodigoProducto": 40151500}]}}
    f = td.parse_chile(x, "https://api.mercadopublico.cl/x", AT)
    assert v(f, "items")[0]["quantity"] == "6 Unidad"
    assert v(f, "clarification_deadline") == "2026-11-21" and v(f, "duration") == ["12 months"]
    assert v(f, "performance_guarantee")["quoted"]


def test_worldbank_text_rules():
    n = {"bid_description": "Supply of vital signs monitors", "submission_deadline_date": "2026-12-10T00:00:00Z",
         "procurement_method_name": "Request for Bids",
         "notice_text": "<p>Lot 1: Vital signs monitors (200 units)</p><p>Lot 2 - Infusion pumps</p>"
                        "<p>All bids must be accompanied by a Bid Security of USD 6,000.</p><p>Qualification requirements: average annual "
                        "turnover of USD 500,000 over the last 3 years.</p><p>Bidding document at https://example.gov.et/docs. "
                        "Contact: officer@example.gov.et, Tel +251 11 123 4567</p>"}
    f = td.parse_worldbank(n, "https://search.worldbank.org/api/v2/procnotices?id=OP1", AT)
    assert v(f, "lots")["count"] == 2
    assert "Bid Security of USD 6,000" in v(f, "bid_security")["quoted"][0]
    assert "turnover" in v(f, "eligibility")[0]["text"]
    assert v(f, "documents")[0]["url"] == "https://example.gov.et/docs"
    assert "officer@" not in json.dumps(f) and "123 4567" not in json.dumps(f)
    assert v(f, "performance_guarantee") == td.NS


def test_selection_and_rates(tmp_path):
    import datetime as dt
    t = dt.date(2026, 11, 12)
    r = {"source": "TED (EU)", "sector": "Power & electrical equipment", "stage": "tender", "deadline": "2026-11-25"}
    assert td.eligible(r, t)
    assert not td.eligible({**r, "deadline": "2026-11-15"}, t)  # less than 7 days left
    assert not td.eligible({**r, "sector": "Education, social & hospitality services"}, t)
    assert not td.eligible({**r, "source": "SAM.gov (USA)"}, t)
    recs = [{"source": "TED (EU)", "fields": {"lots": td.field({"count": 1}, "u", AT, "b"), "items": td.field([{"name": "x", "quantity": "1"}], "u", AT, "b")}},
            {"source": "TED (EU)", "fields": {"lots": td.field("", "u", AT, "b"), "items": td.field([{"name": "y"}], "u", AT, "b")}}]
    rates, per = td.fill_rates(recs)
    assert rates["lots"]["rate"] == 0.5 and rates["quantities"]["rate"] == 0.5 and per["TED (EU)"]["n"] == 2


def test_scrub_and_standards():
    assert td.scrub("Call <b>Mr X</b> on +30 210 123 4567 or x.y@z.gr") == "Call Mr X on [phone] or [e-mail]"
    assert td.standards("EN 2026 and EN 50525-2-31 and IEC 60502-2:2014") == ["EN 50525-2-31", "IEC 60502-2:2014"]
    assert td.incoterms("CIP du département") == [] and td.incoterms("Delivery DDP Valletta") == ["DDP Valletta"]


def test_ted_package_names_and_wb_french():
    for n in ("20261103_2026213/00762189_2026.xml", "762189_2026.xml"):
        m = td.PKG_NAME.search(n)
        assert (int(m.group(1)), m.group(2)) == (762189, "2026")
    t = ("Fourniture en trois (3) lots. Le délai d’exécution de chaque lot est de trois (3) mois calendaires. "
         "Les pondérations suivantes s'appliqueront aux Critères notés : l’offre technique compte pour 50 %.")
    f = td.parse_worldbank({"notice_text": t}, "u", AT)
    assert v(f, "lots") == {"count": 3} and v(f, "evaluation")["quoted"] and v(f, "delivery")["delivery_time_quoted"]


def test_quota_pick_keeps_every_publisher():
    rows = [{"id": f"T{i}", "source": "TED (EU)", "_fit": 90, "est_value_usd": ""} for i in range(100)] + \
           [{"id": f"P{i}", "source": "PNCP (Brazil)", "_fit": 50, "est_value_usd": ""} for i in range(10)]
    got = td.quota_pick(sorted(rows, key=td.priority), 40, floor=5)
    assert len(got) == 40 and sum(1 for r in got if r["source"] == "PNCP (Brazil)") >= 5
