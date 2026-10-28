"""South Africa: National Treasury eTenders OCDS API (no key). All open tenders; sector by keyword."""
import datetime as dt

from .common import cache_empty, clean, log, polite, rolling, session, today
from .sectors import classify
from .taxonomy import group_of_text

URL = "https://ocds-api.etenders.gov.za/api/OCDSReleases"


def fetch(max_pages=80):
    s = session(); t = today()
    days = 30 if cache_empty("za") else 4
    url, params = URL, {"PageNumber": 1, "PageSize": 100, "dateFrom": str(t - dt.timedelta(days=days)), "dateTo": str(t)}
    new, pages = [], 0
    while url and pages < max_pages:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("ZA %s", r.status_code); break
        j = r.json()
        for rel in j.get("releases", []):
            tn = rel.get("tender") or {}
            end = ((tn.get("tenderPeriod") or {}).get("endDate") or "")[:10]
            if end and end < str(t):
                continue
            title = clean(f"{tn.get('title', '')} {tn.get('description', '')}")
            cat = tn.get("mainProcurementCategory") or ""
            sector, method = classify(f"{tn.get('description') or ''} {tn.get('title') or ''}")
            val = tn.get("value") or {}
            new.append({
                "id": f"ZA-{tn.get('id', rel.get('ocid', ''))}", "source": "eTenders (South Africa)",
                "group": group_of_text(tn.get("description") or tn.get("title") or "") or "" if cat == "goods" else "",
                "sector": sector, "nature": cat, "cpv": "", "country": "ZAF",
                "buyer": clean((rel.get("buyer") or {}).get("name"), 120), "title": title[:300],
                "classification": method, "notice_type": clean(tn.get("procurementMethodDetails"), 40), "stage": "tender",
                "access": "National (B-BBEE, local content rules)", "published": (rel.get("date") or "")[:10],
                "deadline": end, "value": val.get("amount") or "", "currency": val.get("currency", "") if val.get("amount") else "",
                "link": f"https://www.etenders.gov.za/Home/opportunities?id={tn.get('id', '')}", "contact": "", "lang": "",
            })
        url = (j.get("links") or {}).get("next")
        polite(0.4)
    rows, _ = rolling("za", new)
    log.info("ZA new %d, open %d (pages %d)", len(new), len(rows), pages)
    return rows, {}
