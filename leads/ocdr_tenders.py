"""Open tenders from the OCP Data Registry (data.open-contracting.org): one connector for every government that
publishes OCDS bulk files (~50 countries, strongest in Latin America, Africa and Asia).

Reads the current-year file of each publication, keeps tenders that are still open (status active/planned, deadline
not passed, not later awarded or cancelled in the same file) and skips countries that already have a dedicated
connector (TED for the EU, SECOP, PNCP, Prozorro ...). Work is spread over runs with a time budget: each run refreshes
the stalest publications; rows from earlier runs are kept until their deadline passes.
Public open data, bulk downloads offered by the registry for reuse.
"""
import datetime as dt
import gzip
import io
import json
import time

from .common import LEADS, log, session, today
from .ocdr import BASE, MAX_BYTES, PRIORITY, _publications
from .ocds import tender_row
from .regions import region

CACHE = LEADS / "cache" / "ocdr_tenders.json"
EU = {"AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU",
      "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"}
COVERED = EU | {"UKR", "PRY", "DOM", "COL", "BRA", "GBR", "KEN", "ZAF", "CAN", "AUS", "USA", "ISR", "SAU", "OMN", "QAT"}
CLOSED = {"complete", "cancelled", "unsuccessful", "withdrawn"}


def _read(s, pub, year, today_s, t_end):
    url = f"{BASE}/publication/{pub['id']}/download?name={year}.jsonl.gz"
    r = s.get(url, stream=True, timeout=120)
    if r.status_code != 200 or int(r.headers.get("content-length") or 0) > MAX_BYTES:
        r.close()
        return None
    src = f"OCDS: {pub['title'][:50]}"
    rows, closed, n = {}, set(), 0
    with gzip.GzipFile(fileobj=r.raw) as gz:
        for line in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            if time.time() > t_end:
                break
            n += 1
            if '"tender"' not in line:
                continue
            try:
                rel = json.loads(line)
            except ValueError:
                continue
            ocid = rel.get("ocid") or ""
            tn = rel.get("tender") or {}
            if tn.get("status") in CLOSED or rel.get("awards") or rel.get("contracts"):
                closed.add(ocid); rows.pop(ocid, None); continue
            if ocid in closed:
                continue
            row = tender_row(rel, source=src, prefix=f"OCT{pub['id']}", country=pub["iso"], today_s=today_s)
            if not row or not (row["title"] or "").strip():
                continue
            if not row["deadline"] and (row["published"] or "") < str(today() - dt.timedelta(days=60)):
                continue  # no deadline and old: most likely closed without a later release in this file
            if not row["link"]:
                row["link"] = f"{BASE}/publication/{pub['id']}"
            prev = rows.get(ocid)
            if not prev or (row["published"] or "") >= (prev["published"] or ""):
                rows[ocid] = row
    r.close()
    return list(rows.values()), n


def fetch():
    s = session()
    t_end = time.time() + 1500
    today_s = str(today())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if not cache.get("pubs") or cache.get("listed", "") < str(today() - dt.timedelta(days=14)):
        cache["pubs"] = _publications(s); cache["listed"] = today_s
    store = cache.setdefault("store", {})
    pubs = [p for p in cache["pubs"] if p.get("iso") and p["iso"] not in COVERED and p.get("years")
            and max(p["years"]) >= today().year - 1]
    pubs.sort(key=lambda p: (store.get(p["id"], {}).get("ran", ""), PRIORITY.get(region(p["iso"]), 2)))
    stats = {"publications": len(pubs), "read": 0, "releases": 0}
    for p in pubs:
        if time.time() > t_end - 60:
            break
        year = max(p["years"])
        try:
            res = _read(s, p, year, today_s, min(t_end, time.time() + 300))
        except Exception as e:  # noqa: BLE001
            log.warning("OCDR tenders %s %s: %s", p["id"], p["iso"], e); res = None
        store[p["id"]] = {"ran": today_s + time.strftime("T%H:%M"), "iso": p["iso"],
                          "rows": res[0] if res else store.get(p["id"], {}).get("rows", [])}
        if res:
            stats["read"] += 1; stats["releases"] += res[1]
            log.info("OCDR tenders %s %s %s: %d open of %d releases", p["id"], p["iso"], year, len(res[0]), res[1])
    out = []
    for v in store.values():  # keep only rows still open
        v["rows"] = [r for r in v.get("rows", []) if not r.get("deadline") or r["deadline"] >= today_s]
        out += v["rows"]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    stats["open_tenders"] = len(out)
    stats["countries"] = len({r["country"] for r in out})
    log.info("OCDR tenders %s", stats)
    return out, stats
