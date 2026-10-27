"""Canada: CanadaBuys open tender notices (open data CSV, no key), goods matched by commodity keywords."""
import csv
import io

from .common import clean, log, session, today
from .taxonomy import group_of_text

URL = "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"


def fetch():
    r = session().get(URL, timeout=180)
    text = r.content.decode("utf-8-sig", errors="ignore")
    rows, t = [], str(today())
    for x in csv.DictReader(io.StringIO(text)):
        if "GD" not in (x.get("procurementCategory-categorieApprovisionnement") or ""):
            continue
        title = clean(x.get("title-titre-eng"))
        gid = group_of_text(f"{title} {x.get('unspscDescription-eng', '')} {x.get('gsinDescription-nibsDescription-eng', '')}")
        if not gid:
            continue
        dl = (x.get("tenderClosingDate-appelOffresDateCloture") or "")[:10]
        if dl and dl < t:
            continue
        rows.append({
            "id": f"CA-{x.get('referenceNumber-numeroReference', '')}", "source": "CanadaBuys (Canada)", "group": gid,
            "country": "CAN", "buyer": clean(x.get("contractingEntityName-nomEntitContractante-eng"), 120),
            "title": title[:300], "classification": clean(x.get("unspscDescription-eng") or x.get("gsin-nibs"), 60),
            "notice_type": clean(x.get("noticeType-avisType-eng"), 40),
            "published": (x.get("publicationDate-datePublication") or "")[:10], "deadline": dl, "value": "",
            "currency": "", "link": x.get("noticeURL-URLavis-eng", ""),
            "contact": clean(f"{x.get('contactInfoEmail-informationsContactCourriel', '')} "
                             f"{x.get('contactInfoPhone-contactInfoTelephone', '')}", 120), "match": "",
        })
    log.info("CanadaBuys rows %d", len(rows))
    return rows, {}
