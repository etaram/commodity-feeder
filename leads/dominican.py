"""Dominican Republic: DGCP open data API (OCDS releases), processes published in the last days."""
import datetime as dt

from .common import CACHE, cache_empty, log, polite, rolling, session, today
from .ocds import tender_row
from .ocds_fetch import releases_of

BASE = "https://datosabiertos.dgcp.gob.do/api-dgcp/v1/ocds/releases"


def fetch():
    s, t = session(), today()
    days = 21 if cache_empty("dominican") else 3
    j = s.get(f"{BASE}/all", params={"limit": 1000, "start_date": str(t - dt.timedelta(days=days)), "end_date": str(t)},
              timeout=120).json()
    items = ((j.get("payload") or {}).get("content")) or []
    known = set((CACHE / "dominican.jsonl").read_text().split('"id": "')[1:]) if (CACHE / "dominican.jsonl").exists() else set()
    known = {k.split('"', 1)[0] for k in known}
    new, n = [], 0
    for it in items:
        oc = it.get("ocid", "")
        if f"DO-{oc}" in known or "-CD-" in oc:  # CD = compras por debajo del umbral / direct
            continue
        try:
            rels = releases_of(s.get(BASE, params={"ocid": oc}, timeout=60).json()); n += 1
        except Exception:  # noqa: BLE001
            continue
        for rel in rels[-1:]:
            row = tender_row(rel, source="DGCP (Dominican Republic)", prefix="DO", country="DOM", lang="es",
                             access="National (foreign firms may bid)", today_s=str(t),
                             link="https://comunidad.comprasdominicana.gob.do/Public/Tendering/ContractNoticeManagement/Index")
            if row:
                new.append(row)
        if n >= 600:
            break
        polite(0.2)
    rows, _ = rolling("dominican", new)
    log.info("Dominican listed %d, fetched %d, new %d, open %d", len(items), n, len(new), len(rows))
    return rows, {"new": len(new), "listed": len(items)}
