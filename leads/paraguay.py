"""Paraguay: DNCP open data API v3 (OCDS). Active tenders, then each record's latest release."""
import time

from .common import CACHE, log, polite, rolling, session, today
from .ocds import tender_row
from .ocds_fetch import releases_of

URL = "https://www.contrataciones.gov.py/datos/api/v3/doc/search/processes"


def fetch():
    s, t = session(), today()
    known = set()
    p = CACHE / "paraguay.jsonl"
    if p.exists():
        known = {line.split('"id": "', 1)[1].split('"', 1)[0] for line in p.read_text().splitlines() if '"id": "' in line}
    new, page, fetched, t0 = [], 1, 0, time.time()
    while page <= 40 and fetched < 700 and time.time() - t0 < 420:
        r = s.get(URL, params={"tender.status": "active", "items_per_page": 100, "page": page}, timeout=90)
        if r.status_code != 200:
            log.warning("PY %s", r.status_code); break
        recs = r.json().get("records") or []
        if not recs:
            break
        for rec in recs:
            rid = f"PY-{rec.get('ocid')}"
            if rid in known or not rec.get("releases"):
                continue
            url = rec["releases"][0].get("url")
            try:
                rels = releases_of(s.get(url, timeout=60).json()); fetched += 1
            except Exception:  # noqa: BLE001
                continue
            for rel in rels[-1:]:
                row = tender_row(rel, source="DNCP (Paraguay)", prefix="PY", country="PRY", lang="es",
                                 access="National (foreign firms may bid)", today_s=str(t),
                                 link=f"https://www.contrataciones.gov.py/licitaciones/convocatoria/{rec.get('ocid', '').split('-')[-2]}.html")
                if row:
                    row["id"] = rid; new.append(row)
            polite(0.2)
        page += 1
    rows, _ = rolling("paraguay", new)
    log.info("Paraguay new %d, open %d (fetched %d)", len(new), len(rows), fetched)
    return rows, {"new": len(new)}
