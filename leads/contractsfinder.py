"""UK Contracts Finder (OCDS search API): below-threshold and local-government opportunities that are not on
Find a Tender."""
import datetime as dt

from .common import cache_empty, log, polite, rolling, session, today
from .ocds import tender_row

URL = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"


def fetch():
    s, t = session(), today()
    days = 21 if cache_empty("contractsfinder") else 3
    new, url, params, pages = [], URL, {"publishedFrom": (t - dt.timedelta(days=days)).isoformat(), "stages": "tender",
                                        "size": 100}, 0
    while url and pages < 60:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("CF %s", r.status_code); break
        j = r.json()
        for rel in j.get("releases", []):
            row = tender_row(rel, source="Contracts Finder (UK)", prefix="CF", country="GBR", access="National (UK)",
                             today_s=str(t),
                             link=f"https://www.contractsfinder.service.gov.uk/Notice/{rel.get('id', '').split('-', 1)[-1]}")
            if row:
                new.append(row)
        url = (j.get("links") or {}).get("next")
        polite(0.4)
    rows, _ = rolling("contractsfinder", new)
    log.info("Contracts Finder new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
