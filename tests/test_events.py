"""Checks for leads/events.py and leads/hypotheses.py: typing, dedup of a republished item, linking.
Run: python -m tests.test_events   (fakes only, writes nothing)"""
import datetime as dt

from leads import events as E
from leads import hypotheses as H

T = dt.date(2026, 11, 5)


def news(date, title, source, url="https://news.google.com/rss/articles/x", countries=("KEN",)):
    return {"date": date, "title": title, "summary": "", "source": source, "url": url, "countries": list(countries), "lead": "", "group": "", "topic": "t"}


def check_typing():
    c = lambda s: E.classify(s)[0]
    assert c("World Bank approves $300 million loan for Kenya rural roads") == "financing_approval"
    assert c("PowerChina selected as EPC contractor for Tanzania 400kV line") == "epc_selection"
    assert c("Copper prices hit record high on supply fears") == "material_price_logistics"
    assert c("Infosys share price jumps 4%") == "", "equity prices are not material prices"
    assert c("US imposes new tariffs on steel imports from Vietnam") == "trade_policy_change"
    assert c("Port strike halts container loadings at Durban") == "supply_disruption"
    assert c("Licitacion publica para el suministro de transformadores") == "tender_publication", "Spanish tender words"
    assert c("Avis rectificatif - fourniture de compteurs") == "tender_amendment", "French amendment words"
    assert c("Masdar starts construction on 200MW solar project in Malaysia") == "construction_start"
    assert c("Boy who survived tsunami signs pro soccer contract") == "", "sports contracts are not awards"
    assert E.money_usd("Kenya secures US$1.2 billion financing") == 1_200_000_000
    assert E.money_usd("built in 2026 with 300 workers") == 0, "a bare number is not money"
    assert E.supplier_country("China's Yingfa unveils 7.5-GW solar cell plant in Indonesia", "") == "CHN"


def check_dedup_and_republish():
    first = [news("2026-10-01", "Kenya approves $500 million loan for Nairobi water project", "Reuters"),
             news("2026-10-02", "Kenya approves $500 million loan for Nairobi water project", "Business Daily"),  # mirrored copy
             news("2026-10-02", "Nairobi water project gets $500 million loan approval from Kenya cabinet", "The East African")]  # independent
    evs, st = E.news_events(first, T)
    fin = [e for e in evs if e["type"] == "financing_approval"]
    assert len(fin) == 1, f"three reports, one event (got {len(fin)})"
    assert fin[0]["mirrors"] == 1 and fin[0]["independent_sources"] == 2, (fin[0]["mirrors"], fin[0]["independent_sources"])
    assert st["mirrored_copies"] == 1 and st["independent_confirmations"] == 1
    out1, s1 = E.change_detect(evs, [], T)
    assert s1["new"] == len(evs)
    prev = [{k: ("" if k.startswith("_") else str(v)) for k, v in e.items() if not k.startswith("_")} for e in out1]
    # the same announcement three weeks later from a new outlet: not a new event
    again, _ = E.news_events([news("2026-10-25", "Kenya approves $500 million loan for Nairobi water project", "Capital FM")], T)
    out2, s2 = E.change_detect(again, prev, T)
    hit = [e for e in out2 if e["type"] == "financing_approval" and e["change"] != "carried"]
    assert len(hit) == 1 and hit[0]["change"] == "republished", [(e["change"], e["title"]) for e in out2]
    assert hit[0]["event_id"] == fin[0]["event_id"] and hit[0]["event_date"] == "2026-10-01", "keeps the original id and date"
    assert s2.get("new", 0) == 0


def tender(**kw):
    r = {"id": "", "source": "", "stage": "tender", "notice_type": "", "country": "KEN", "title_en": "", "buyer": "", "est_value_usd": "",
         "link": "", "_pub": "", "_first": "2026-10-01", "access": "International", "deadline": "", "days_left": "", "score": "50", "sector": ""}
    r.update(kw)
    return r


def check_linking():
    rows = [tender(id="WBP-P999001", source="World Bank pipeline", stage="planned", notice_type="Project Active",
                   title_en="Kenya Last Mile Energy Access Project (Power)", buyer="Kenya Power", est_value_usd="250000000",
                   _pub="2026-05-01", sector="Power & electrical equipment"),
            tender(id="WB-OP1", source="World Bank", notice_type="Invitation for Bids", buyer="Kenya Power PIU",
                   title_en="Supply of distribution transformers | Kenya Last Mile Energy Access Project", deadline="2026-12-01"),
            tender(id="SAM-a", source="SAM.gov (USA)", stage="planned", notice_type="Presolicitation", country="USA",
                   buyer="DEPT OF THE NAVY", title_en="Diesel generator sets 500 kW"),
            tender(id="SAM-b", source="SAM.gov (USA)", notice_type="Solicitation", country="USA", buyer="DEPT OF THE NAVY",
                   title_en="Diesel generator sets 500 kW", est_value_usd="200000000", access="open to foreign firms")]
    wb_awards = [{"project_id": "P999001", "project": "Kenya Last Mile Energy Access Project", "country": "KEN", "practice": "Energy",
                  "usd": "3000000", "signed": "2026-10-10", "supplier": "ACME CABLES", "supplier_country": "IND", "category": "Goods",
                  "description": "Supply of LV cables", "method": "RFB"}]
    rec, projects, _ = E.record_events(rows, wb_awards, [], [], T)
    keys = {e["record_id"]: e["project_key"] for e in rec}
    assert keys["WBP-P999001"] == "WB:P999001"
    assert keys["WB-OP1"] == "WB:P999001", "open WB notice linked by project name"
    assert any(e["type"] == "award" and e["project_key"] == "WB:P999001" and e["supplier_country"] == "IND" for e in rec)
    assert E.link_buyer_title(rec, projects) >= 1
    sam = {e["record_id"]: e for e in rec if e["record_id"].startswith("SAM")}
    assert sam["SAM-b"]["project_key"] == sam["SAM-a"]["project_key"] == "T:SAM-a", "planned row -> its open tender"
    out, _ = E.change_detect(rec, [], T)
    tl = E.build_timelines(out, projects, wb_awards, T)
    x = tl["WB:P999001"]
    assert x["financing_date"] == "2026-05-01" and x["open_tenders"] == 1 and x["stage"] == "awarded", x
    # hypotheses: the financed project with an open tender is actionable; without it, a research candidate
    tl_rows = [{k: str(v) for k, v in x.items()}]
    ev_rows = [{k: ("" if k.startswith("_") else str(v)) for k, v in e.items() if not k.startswith("_")} for e in out]
    fake = {"project_timelines.csv": tl_rows, "events.csv": ev_rows, "wb_awards.csv": wb_awards, "hypotheses.csv": []}
    orig = H._rows
    H._rows = lambda name: fake.get(name, [])
    try:
        hs, _ = H.build(write=False)
        a = [h for h in hs if h["project_key"] == "WB:P999001"]
        assert a and a[0]["status"] == "actionable" and a[0]["tender_id"] == "WB-OP1", a
        tl_rows[0].update(open_tenders="0", open_tender_ids="", goods_works_awards="0", stage="financing approved")
        hs, _ = H.build(write=False)
        r = [h for h in hs if h["project_key"] == "WB:P999001"]
        assert r and r[0]["status"] == "research candidate" and r[0]["rule"] == "financed_no_tender" and not r[0]["tender_id"], r
        assert r[0]["missing_info"] and r[0]["next_action"] and r[0]["label"].startswith("HYPOTHESIS")
    finally:
        H._rows = orig


if __name__ == "__main__":
    check_typing()
    check_dedup_and_republish()
    check_linking()
    print("events: all checks passed")
