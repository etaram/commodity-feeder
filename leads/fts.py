"""UK Find a Tender service (OCDS API, free, no key): open goods tenders matched to the groups by CPV."""
import datetime as dt

from .common import clean, log, polite, session, today
from .taxonomy import match_cpv

URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"


def fetch(days=14, max_pages=80):
    s = session(); t = today()
    url = URL; params = {"stages": "tender", "limit": 100,
                         "updatedFrom": (t - dt.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")}
    rows, seen, pages = [], set(), 0
    while url and pages < max_pages:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("FTS %s", r.status_code); break
        j = r.json()
        for rel in j.get("releases", []):
            tn = rel.get("tender") or {}
            if tn.get("status") not in ("active", "planned") or tn.get("mainProcurementCategory") != "goods":
                continue
            cpv = [(tn.get("classification") or {}).get("id", "")]
            for it in tn.get("items") or []:
                cpv += [c.get("id", "") for c in it.get("additionalClassifications") or [] if c.get("scheme") == "CPV"]
            gid, depth = match_cpv([c for c in cpv if c])
            if not gid:
                continue
            ocid = rel.get("ocid", "")
            if ocid in seen:
                continue
            seen.add(ocid)
            end = ((tn.get("tenderPeriod") or {}).get("endDate") or "")[:10]
            if end and end < str(t):
                continue
            buyer = (rel.get("buyer") or {}).get("name", "")
            cp = next(((p.get("contactPoint") or {}) for p in rel.get("parties") or [] if "buyer" in (p.get("roles") or [])), {})
            val = (tn.get("value") or {})
            rows.append({
                "id": f"FTS-{ocid}", "source": "Find a Tender (UK)", "group": gid, "country": "GBR",
                "buyer": clean(buyer, 120), "title": clean(f"{tn.get('title', '')} | {tn.get('description', '')}", 300),
                "classification": " ".join(dict.fromkeys(c for c in cpv if c))[:60], "notice_type": "tender",
                "published": (rel.get("date") or "")[:10], "deadline": end,
                "value": val.get("amount", ""), "currency": val.get("currency", "") if val.get("amount") else "",
                "link": f"https://www.find-tender.service.gov.uk/Notice/{rel.get('id', '')}",
                "contact": clean(f"{cp.get('email', '')} {cp.get('telephone', '')}", 120), "match": depth,
            })
        url = (j.get("links") or {}).get("next")
        polite(0.5)
    log.info("FTS rows %d (pages %d)", len(rows), pages)
    return rows, {"pages": pages}
