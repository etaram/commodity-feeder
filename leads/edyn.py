"""European Dynamics e-procurement portals with an OCDS record-package service (Ghana GHANEPS, Zambia ZPPA).
Reads the current and previous month packages."""
import io
import json
import zipfile

from .common import log, rolling, session, today
from .ocds import tender_row
from .ocds_fetch import releases_of

PORTALS = {"ghana": ("https://www.ghaneps.gov.gh", "GHANEPS (Ghana)", "GH", "GHA"),
           "zambia": ("https://www.zppa.org.zm", "ZPPA (Zambia)", "ZM", "ZMB")}


def fetch_portal(key):
    base, source, prefix, country = PORTALS[key]
    s, t = session(), today()
    lst = s.get(f"{base}/ocds/services/recordpackage/getrecordpackagelist", timeout=90).json()
    urls = (lst.get("packagesPerMonth") or [])[-2:]
    new = []
    for u in urls:
        r = s.get(u, timeout=180)
        if r.status_code != 200:
            log.warning("%s %s %s", key, u, r.status_code); continue
        blobs = []
        if r.content[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(r.content)); blobs = [z.read(n) for n in z.namelist()]
        else:
            blobs = [r.content]
        for b in blobs:
            try:
                rels = releases_of(json.loads(b))
            except ValueError:
                continue
            for rel in rels:
                row = tender_row(rel, source=source, prefix=prefix, country=country, access="National (foreign firms may bid)",
                                 today_s=str(t), link=f"{base}/epps/home.do")
                if row:
                    new.append(row)
    rows, _ = rolling(key, new)
    log.info("%s new %d, open %d", key, len(new), len(rows))
    return rows, {"new": len(new)}


class _Mod:
    def __init__(self, key):
        self.key = key

    def fetch(self):
        return fetch_portal(self.key)
