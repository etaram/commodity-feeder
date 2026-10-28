"""UK Find a Tender service (OCDS API, free, no key): all open tenders (goods, works, services), sector by CPV.
Rolling cache: each run reads notices updated in the last few days."""
import datetime as dt

from .common import cache_empty, clean, log, polite, rolling, session, today
from .sectors import from_cpv
from .taxonomy import match_cpv

URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"


def fetch(max_pages=150):
    s = session(); t = today()
    days = 30 if cache_empty("fts") else 3
    url = URL; params = {"stages": "tender", "limit": 100,
                         "updatedFrom": (t - dt.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")}
    new, pages = [], 0
    while url and pages < max_pages:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("FTS %s", r.status_code); break
        j = r.json()
        for rel in j.get("releases", []):
            tn = rel.get("tender") or {}
            if tn.get("status") not in ("active", "planned"):
                continue
            cpv = [(tn.get("classification") or {}).get("id", "")]
            for it in tn.get("items") or []:
                cpv += [c.get("id", "") for c in it.get("additionalClassifications") or [] if c.get("scheme") == "CPV"]
            cpv = [c for c in dict.fromkeys(cpv) if c]
            gid, depth = match_cpv(cpv[:1])
            ocid = rel.get("ocid", "")
            end = ((tn.get("tenderPeriod") or {}).get("endDate") or "")[:10]
            if end and end < str(t):
                continue
            buyer = (rel.get("buyer") or {}).get("name", "")
            cp = next(((p.get("contactPoint") or {}) for p in rel.get("parties") or [] if "buyer" in (p.get("roles") or [])), {})
            val = (tn.get("value") or {})
            new.append({
                "id": f"FTS-{ocid}", "source": "Find a Tender (UK)", "group": gid or "", "match": depth if gid else "",
                "sector": from_cpv(cpv[:1]) or "", "nature": tn.get("mainProcurementCategory", ""),
                "cpv": " ".join(cpv[:6]), "country": "GBR", "buyer": clean(buyer, 120),
                "title": clean(f"{tn.get('title', '')} | {tn.get('description', '')}", 300),
                "classification": " ".join(cpv[:6]), "notice_type": "planned" if tn.get("status") == "planned" else "tender",
                "stage": "planned" if tn.get("status") == "planned" else "tender", "access": "GPA open",
                "published": (rel.get("date") or "")[:10], "deadline": end,
                "value": val.get("amount", ""), "currency": val.get("currency", "") if val.get("amount") else "",
                "link": f"https://www.find-tender.service.gov.uk/Notice/{rel.get('id', '')}", "lang": "",
                "contact": clean(f"{cp.get('email', '')} {cp.get('telephone', '')}", 120),
            })
        url = (j.get("links") or {}).get("next")
        polite(0.4)
    rows, _ = rolling("fts", new)
    log.info("FTS new %d, open %d (pages %d)", len(new), len(rows), pages)
    return rows, {"pages": pages}
