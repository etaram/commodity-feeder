"""Moldova: MTender (mtender.gov.md) open OCDS API. Lists tenders changed since a date, then reads each record."""
import concurrent.futures as cf
import datetime as dt
import re

from .common import cache_empty, log, rolling, session, today
from .ocds import tender_row
from .ocds_fetch import releases_of

BASE = "https://public.mtender.gov.md/tenders/"


def _one(s, ocid, t):
    try:
        r = s.get(BASE + ocid, timeout=60)
        if r.status_code != 200:
            return None
        best = None
        for rel in releases_of(r.json()):
            row = tender_row(rel, source="MTender (Moldova)", prefix="MD", country="MDA", lang="ro",
                             access="National (foreign firms may bid)", today_s=str(t), link=f"https://mtender.gov.md/tenders/{ocid}")
            # only notices with a submission deadline (open tenders) or true planning notices; bare "active" planning
            # records carry no deadline and are mostly tenders that already ran
            if row and (row["deadline"] or row["stage"] == "planned") and (best is None or (row["deadline"] and not best["deadline"])):
                best = row
        if best:
            best["id"] = f"MD-{ocid}"
        return best
    except Exception:  # noqa: BLE001
        return None


def fetch():
    s, t = session(), today()
    days = 14 if cache_empty("moldova") else 3
    off = (dt.datetime.utcnow() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    ocids, pages = [], 0
    while off and pages < 80:
        r = s.get(BASE, params={"offset": off}, timeout=60); pages += 1
        if r.status_code != 200:
            log.warning("MTender list %s", r.status_code); break
        j = r.json(); data = j.get("data") or []
        if not data:
            break
        # one tender has several records (planning, notice, evaluation); keep the root ocid once
        for d in data:
            m = re.match(r"(ocds-b3wdp1-MD-\d+)", d.get("ocid", ""))
            if m and m.group(1) not in ocids:
                ocids.append(m.group(1))
        nxt = j.get("offset")
        if nxt == off:
            break
        off = nxt
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda o: _one(s, o, t), ocids[:4000]))
    new = [x for x in res if x]
    rows, _ = rolling("moldova", new)
    log.info("MTender new %d, open %d (ocids %d, pages %d)", len(new), len(rows), len(ocids), pages)
    return rows, {"new": len(new)}
