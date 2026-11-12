"""Singapore GeBIZ government procurement awards (data.gov.sg dataset d_acde1106003906a75c3fa052592f2fcb, "Government
Procurement via GeBIZ", Singapore Open Data Licence v1.0 https://data.gov.sg/open-data-licence: commercial reuse
allowed with attribution; data.gov.sg robots.txt "Allow: /", both checked 2026-11-12). ~18,500 awards since April
2021 with agency, tender description, supplier name and awarded amount (SGD); the dataset is refreshed about once a
year, so a full read is repeated only when the record count changes or every 30 days.

Writes award day files data/leads/awards/gebiz/YYYY-MM-DD.json (by award date). Award dates in the future are
quarantined. "Awarded to No Suppliers" rows are skipped."""
import datetime as dt
import json
import re

from .common import PRIVATE, clean, log, polite, quarantine_future, save_awards, session, today
from .sectors import classify

RESOURCE = "d_acde1106003906a75c3fa052592f2fcb"
API = "https://data.gov.sg/api/action/datastore_search"
SOURCE_URL = "https://data.gov.sg/datasets/d_acde1106003906a75c3fa052592f2fcb/view"
PAGE = 1000
KEEP_DAYS = 365 * 8
STATE = PRIVATE / "gebiz_awards_state.json"
SG_FIRM = re.compile(r"\bPTE\.?\s*LTD\b|\bPTE\b|\bSINGAPORE\b|\bLLP\b", re.I)


def _date(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""


def to_row(x, fetched):
    name = clean(x.get("supplier_name"), 160)
    if not name or "no supplier" in (x.get("tender_detail_status") or "").lower() or name.lower() in ("unknown", "na", "n.a."):
        return None
    title = clean(x.get("tender_description"), 300)
    sector, _ = classify(title)
    try:
        val = float(x.get("awarded_amt") or 0) or ""
    except ValueError:
        val = ""
    tno = clean(x.get("tender_no"), 40)
    return {"id": f"GEBIZ-{tno}-{re.sub(r'[^A-Z0-9]', '', name.upper())[:30]}", "source": "GeBIZ (Singapore)", "group": "", "sector": sector,
            "title": title[:200], "buyer": clean(x.get("agency"), 120), "country": "SGP", "cpv": "", "published": _date(x.get("award_date")),
            "winners": [name], "winner_country": "SGP" if SG_FIRM.search(name) else "", "winner_size": "", "value": val,
            "currency": "SGD" if val else "", "bids": "", "email": "", "link": SOURCE_URL, "source_url": SOURCE_URL, "fetched": fetched,
            "tender_no": tno, "status": clean(x.get("tender_detail_status"), 60)}


def fetch():
    s, t = session(), str(today())
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    head = s.get(API, params={"resource_id": RESOURCE, "limit": 1}, timeout=60).json()["result"]
    total = int(head.get("total") or 0)
    if st.get("total") == total and st.get("run", "") >= str(today() - dt.timedelta(days=30)):
        log.info("GeBIZ awards: unchanged (%d records, read %s)", total, st.get("run"))
        return [], {"awards": 0, "note": "fresh", "total": total}
    rows, offset = [], 0
    while offset < total:
        polite(2)
        r = s.get(API, params={"resource_id": RESOURCE, "limit": PAGE, "offset": offset}, timeout=90)
        r.raise_for_status()
        recs = r.json()["result"]["records"]
        if not recs:
            break
        rows += [a for a in (to_row(x, t) for x in recs) if a]
        offset += len(recs)
    rows, quarantined = quarantine_future(rows, "gebiz_awards")
    n = save_awards("gebiz", rows, keep_days=KEEP_DAYS) if rows else 0
    PRIVATE.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"total": total, "run": t}))
    log.info("GeBIZ awards: %d awards with a supplier from %d records, %d quarantined", n, total, quarantined)
    return [], {"awards": n, "total": total, "quarantined": quarantined}
