"""South Africa: National Treasury eTenders OCDS API (no key), open goods tenders matched by keywords."""
import datetime as dt

from .common import clean, log, polite, session, today
from .taxonomy import group_of_text

URL = "https://ocds-api.etenders.gov.za/api/OCDSReleases"


def fetch(days=21, max_pages=40):
    s = session(); t = today(); rows, seen = [], set()
    url, params = URL, {"PageNumber": 1, "PageSize": 100, "dateFrom": str(t - dt.timedelta(days=days)), "dateTo": str(t)}
    pages = 0
    while url and pages < max_pages:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("ZA %s", r.status_code); break
        j = r.json()
        for rel in j.get("releases", []):
            tn = rel.get("tender") or {}
            if tn.get("mainProcurementCategory") != "goods" or rel.get("ocid") in seen:
                continue
            title = clean(f"{tn.get('title', '')} {tn.get('description', '')}")
            gid = group_of_text(tn.get("description") or tn.get("title") or "")
            if not gid:
                continue
            end = ((tn.get("tenderPeriod") or {}).get("endDate") or "")[:10]
            if end and end < str(t):
                continue
            seen.add(rel.get("ocid"))
            val = tn.get("value") or {}
            rows.append({
                "id": f"ZA-{tn.get('id', '')}", "source": "eTenders (South Africa)", "group": gid, "country": "ZAF",
                "buyer": clean((rel.get("buyer") or {}).get("name"), 120), "title": title[:300],
                "classification": "keyword", "notice_type": clean(tn.get("procurementMethodDetails"), 40),
                "published": (rel.get("date") or "")[:10], "deadline": end,
                "value": val.get("amount") or "", "currency": val.get("currency", "") if val.get("amount") else "",
                "link": f"https://www.etenders.gov.za/Home/opportunities?id={tn.get('id', '')}", "contact": "", "match": "",
            })
        url = (j.get("links") or {}).get("next")
        polite(0.5)
    log.info("ZA rows %d (pages %d)", len(rows), pages)
    return rows, {}
