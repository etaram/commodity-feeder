"""Tanzania: NeST (National e-Procurement System) OCDS data portal, releases since a recent date."""
import datetime as dt

from .common import cache_empty, log, polite, rolling, session, today
from .ocds import tender_row

URL = "https://nest.go.tz/gateway/nest-data-portal-api/api/releases"


def fetch():
    s, t = session(), today()
    since = (dt.datetime.utcnow() - dt.timedelta(days=21 if cache_empty("tanzania") else 3)).strftime("%Y-%m-%dT%H:%M:%S")
    url, params, new, pages = URL, {"since": since}, [], 0
    while url and pages < 80:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("NeST %s", r.status_code); break
        j = r.json(); rels = j.get("releases") or []
        if not rels:
            break
        for rel in rels:
            row = tender_row(rel, source="NeST (Tanzania)", prefix="TZ", country="TZA", access="National (local preference)",
                             today_s=str(t), link="https://nest.go.tz/tenders")
            if row:
                new.append(row)
        url = (j.get("links") or {}).get("next")
        polite(0.3)
    rows, _ = rolling("tanzania", new)
    log.info("NeST new %d, open %d (pages %d)", len(new), len(rows), pages)
    return rows, {"new": len(new)}
