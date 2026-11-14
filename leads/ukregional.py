"""UK devolved portals: Public Contracts Scotland (PCS) and Sell2Wales, through their public OCDS notice APIs
(api.publiccontractsscotland.gov.uk/v1/Notices, api.sell2wales.gov.wales/v1/Notices; same platform). They carry the
lower-value (below threshold) Scottish and Welsh tenders that do not reach Find a Tender or Contracts Finder, plus
contract notices. Fields come from OCDS: buyer, title, description, CPV, value, tender period end, official link.

Access (checked 2026-11-14): public JSON, no key. One request per portal, notice type and publication month (the
current and previous MONTHS months). OPEN = a tender-stage release with a submission deadline today or later.
Notices also published on Find a Tender are folded by the merge's duplicate check (same title, buyer, country)."""
import datetime as dt
import time

from .common import log, quarantine_future, session, snapshot, today
from .ocds import tender_row

PORTALS = [("PCS", "https://api.publiccontractsscotland.gov.uk/v1/Notices", "SC", "Public Contracts Scotland"),
           ("S2W", "https://api.sell2wales.gov.wales/v1/Notices", "WL", "Sell2Wales")]
TYPES = [2, 5, 21, 24, 51]   # contract notice, utilities, social services, concession, site (quick-quote / below threshold) ITT
MONTHS = 3


def fetch():
    s, t = session(), today()
    ts = str(t)
    months, d = [], t.replace(day=1)
    for _ in range(MONTHS):
        months.append(d.strftime("%m-%Y")); d = (d - dt.timedelta(days=1)).replace(day=1)
    out, meta, calls = [], {}, 0
    for key, url, prefix, name in PORTALS:
        got, failed = 0, 0
        for nt in TYPES:
            for m in months:
                try:
                    r = s.get(url, params={"dateFrom": m, "noticeType": nt, "outputType": 0, "locale": 2057}, timeout=90)
                    calls += 1
                    if r.status_code == 404 or not r.text.strip():
                        continue
                    r.raise_for_status()
                    rel = (r.json() or {}).get("releases") or []
                except Exception as e:  # noqa: BLE001
                    log.warning("%s type %s %s: %s", key, nt, m, str(e)[:100]); failed += 1; continue
                for x in rel:
                    row = tender_row(x, source=f"{name} (UK)", prefix=prefix, country="GBR", lang="en",
                                     access="UK public procurement (open to suppliers per notice)", today_s=ts)
                    if row and row.get("deadline") and row["deadline"] >= ts and row.get("stage", "tender") == "tender":
                        row["notice_type"] = (row.get("notice_type") or "") + (" | below threshold (site notice)" if nt == 51 else "")
                        out.append(row); got += 1
                time.sleep(0.5)
        meta[f"{key}_rows"], meta[f"{key}_failed"] = got, failed
    if not out and sum(v for k, v in meta.items() if k.endswith("_failed")):
        raise RuntimeError("UK regional portals: nothing read; previous snapshot kept")
    out, q = quarantine_future(out, "ukregional")
    keep, _ = snapshot("ukregional", list({x["id"]: x for x in out}.values()))
    log.info("UK regional portals: %d open (%s, %d calls)", len(keep), ", ".join(f"{k} {v}" for k, v in meta.items()), calls)
    meta.update(new=len(keep), quarantined=q, parts_failed=sum(1 for k, v in meta.items() if k.endswith("_failed") and v))
    return keep, meta
