"""Poland: national procurement notices (Biuletyn Zamowien Publicznych, BZP) from the public e-Zamowienia notice board
API (ezamowienia.gov.pl/mo-board/api/v1/Board/Search): contract notices below the EU thresholds, which TED does not
carry. Fields: notice number, object of the order, buyer, city, CPV, order type, publication date, offer deadline,
link to the official notice.

Access (checked 2026-11-14): public JSON, no key, robots.txt sets no rule. One request per publication day and page,
politely (0.5 s apart). OPEN = a contract notice not marked outdated with an offer deadline today or later."""
import datetime as dt
import re
import time

from .common import clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

API = "https://ezamowienia.gov.pl/mo-board/api/v1/Board/Search"
NOTICE = "https://ezamowienia.gov.pl/mo-board/bzp/notice-details/id/{}"
DAYS = 60
PAGE = 250
NATURE = {"Delivery": "goods", "Services": "services", "Works": "works"}


def parse(items, fetched, t):
    rows = []
    for x in items:
        oid, title = x.get("objectId") or "", clean(x.get("orderObject") or "").strip("„”\" ")
        dl = (x.get("submittingOffersDate") or "")[:10]
        if not oid or not title or x.get("noticeType") != "ContractNotice" or x.get("outdated") or not dl or dl < t:
            continue
        cpv = ",".join(re.findall(r"\b\d{8}-\d\b", x.get("cpvCode") or ""))
        sector, how = classify(title)
        city = clean(x.get("organizationCity") or "")
        rows.append({"id": "PL-BZP-" + re.sub(r"[^A-Za-z0-9]+", "-", x.get("bzpNumber") or oid).strip("-")[:80],
                     "source": "e-Zamowienia BZP (Poland)", "group": "", "sector": sector,
                     "nature": NATURE.get(x.get("orderType") or "", ""), "cpv": cpv, "classification": how, "country": "POL",
                     "buyer": (clean(x.get("organizationName") or "") + (f", {city}" if city else ""))[:120],
                     "title": title[:300], "notice_type": "Contract notice (national, below EU threshold)", "stage": "tender",
                     "access": "Polish public procurement (EU firms may bid; Polish-language documents)",
                     "published": (x.get("publicationDate") or "")[:10], "deadline": dl, "deadline_basis": "submission",
                     "deadline_time": (x.get("submittingOffersDate") or "")[11:16] + " UTC",
                     "value": "", "currency": "", "link": NOTICE.format(oid), "source_url": API,
                     "fetched": fetched, "contact": "", "lang": "pl"})
    return rows


def fetch():
    s, t = session(), today()
    ts = str(t)
    out, calls, failed_days = [], 0, 0
    for back in range(DAYS, -1, -1):
        d, d2 = str(t - dt.timedelta(days=back)), str(t - dt.timedelta(days=back - 1))
        page = 1
        while page <= 120:
            try:
                r = s.get(API, params={"NoticeType": "ContractNotice", "PublicationDateFrom": d, "PublicationDateTo": d2,
                                       "PageSize": PAGE, "PageNumber": page}, timeout=60)
                calls += 1
                r.raise_for_status()
                items = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("Poland BZP %s page %d: %s", d, page, str(e)[:100]); failed_days += 1; break
            if not isinstance(items, list) or not items:
                break
            out += parse(items, ts, ts)
            # the board returns its own page size (not always PageSize): keep paging until a page comes back empty

            page += 1
            time.sleep(0.5)
        time.sleep(0.5)
    if not out and failed_days:
        raise RuntimeError("Poland BZP: no rows read; previous snapshot kept")
    out, q = quarantine_future(out, "poland")
    keep, _ = snapshot("poland", list({x["id"]: x for x in out}.values()))
    log.info("Poland BZP: %d open contract notices (%d calls, %d days failed)", len(keep), calls, failed_days)
    return keep, {"new": len(keep), "calls": calls, "quarantined": q, "parts_failed": failed_days,
                  "complete_snapshot": 0 if failed_days else 1}
