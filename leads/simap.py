"""Switzerland - simap.ch, the national public procurement platform, official open API (www.simap.ch/api-doc).
Open-procedure tender publications of the last 45 days (parameters as used by the simap-mcp project). Notices carry no
deadline in the search result, so they are kept 60 days after publication. Rolling store."""
import datetime as dt

from .common import clean, log, polite, rolling, session, today
from .sectors import classify

API = "https://www.simap.ch/api/publications/v2/project/project-search"


def tr(x):
    if isinstance(x, dict):
        return clean(x.get("en") or x.get("de") or x.get("fr") or x.get("it") or next(iter(x.values()), ""))
    return clean(x or "")


def fetch():
    s, t = session(), today()
    frm = str(t - dt.timedelta(days=45))
    new, last = [], None
    for page in range(12):
        params = {"newestPublicationFrom": frm, "newestPubTypes": "tender", "processTypes": "open"}
        if last:
            params["lastItem"] = last
        try:
            r = s.get(API, params=params, timeout=90)
            r.raise_for_status()
            d = r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("SIMAP page %d: %s", page, str(e)[:150]); break
        for p in d.get("projects", []):
            title = tr(p.get("title"))
            if not title:
                continue
            pid = str(p.get("id"))
            sector, method = classify(title)
            addr = p.get("orderAddress") or {}
            new.append({
                "id": "CH-" + pid, "source": "simap.ch", "group": "", "sector": sector, "nature": "", "cpv": "", "classification": method,
                "country": "CHE", "buyer": tr(p.get("procOfficeName")) or "Swiss public buyer", "title": title[:300],
                "notice_type": str(p.get("projectSubType") or "Tender").title(), "stage": "tender",
                "access": "Open procedure (Swiss public procurement, WTO GPA applies to many notices)",
                "published": str(p.get("publicationDate") or "")[:10], "deadline": "", "value": "", "currency": "",
                "link": f"https://www.simap.ch/en/project-detail/{pid}", "contact": "", "lang": "",
            })
        last = (d.get("pagination") or {}).get("lastItem")
        if not last or not d.get("projects"):
            break
        polite(1)
    rows, _ = rolling("simap", new, max_age_days=60)
    log.info("SIMAP new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
