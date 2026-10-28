"""Canada: CanadaBuys open tender notices (open data CSV, no key). All categories; sector from UNSPSC/GSIN text."""
import csv
import io

from .common import clean, log, session, today
from .sectors import classify
from .taxonomy import group_of_text

URL = "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
CAT = {"GD": "goods", "CNST": "works", "SRV": "services", "SRVTGD": "services"}


def fetch():
    r = session().get(URL, timeout=180)
    text = r.content.decode("utf-8-sig", errors="ignore")
    rows, t = [], str(today())
    for x in csv.DictReader(io.StringIO(text)):
        title = clean(x.get("title-titre-eng"))
        dl = (x.get("tenderClosingDate-appelOffresDateCloture") or "")[:10]
        if dl and dl < t:
            continue
        cat = (x.get("procurementCategory-categorieApprovisionnement") or "").strip("*").split("*")[0]
        unspsc = (x.get("unspsc") or "").split("*")[0].strip()
        desc = f"{x.get('unspscDescription-eng', '')} {x.get('gsinDescription-nibsDescription-eng', '')}"
        sector, method = classify(f"{title} {desc}", unspsc=unspsc)
        rows.append({
            "id": f"CA-{x.get('referenceNumber-numeroReference', '')}", "source": "CanadaBuys (Canada)",
            "group": group_of_text(f"{title} {desc}") or "" if cat == "GD" else "", "sector": sector,
            "nature": CAT.get(cat, ""), "cpv": "", "country": "CAN",
            "buyer": clean(x.get("contractingEntityName-nomEntitContractante-eng"), 120),
            "title": title[:300], "classification": clean(x.get("unspscDescription-eng") or x.get("gsin-nibs"), 60) or method,
            "notice_type": clean(x.get("noticeType-avisType-eng"), 40), "stage": "tender",
            "access": "Trade agreements (CFTA/CETA/WTO-GPA)" if x.get("tradeAgreements-accordsCommerciaux-eng") else "National",
            "published": (x.get("publicationDate-datePublication") or "")[:10], "deadline": dl, "value": "",
            "currency": "", "link": x.get("noticeURL-URLavis-eng", ""), "lang": "",
            "contact": clean(f"{x.get('contactInfoEmail-informationsContactCourriel', '')} "
                             f"{x.get('contactInfoPhone-contactInfoTelephone', '')}", 120), "match": "",
        })
    log.info("CanadaBuys rows %d", len(rows))
    return rows, {}
