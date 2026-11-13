"""Eskom Tender Bulletin (South Africa, state electricity utility; also Eskom Enterprises and Rotek): the public list
behind https://tenderbulletin.eskom.co.za/, read from the JSON the page itself loads
(/webapi/api/Lookup/GetTender?TENDER_ID= with an empty id returns every published notice): reference, header,
scope, division, province, office, closing and published dates, audience, e-tendering flag. 352 published records on
13 Nov 2026 (Grok), about 265 with a closing date in the next 90 days.

Quality rules: a notice titled as a cancellation, regret letter or award is not an opportunity and is left out; a
notice published more than a year ago is left out even when its closing date is far ahead (old rate contracts
re-posted as "as and when required"); OPEN = a future closing date. The officer e-mail in the feed is not kept.
Access (checked 2026-11-13 from the server): public, no sign-in, one request per run. Bidding is on
etendering.eskom.co.za and needs a CSD number; reading the bulletin does not."""
import datetime as dt
import re

from .common import clean, log, quarantine_future, rolling, session, today
from .sectors import classify

URL = "https://tenderbulletin.eskom.co.za/webapi/api/Lookup/GetTender?TENDER_ID="
NOT_OPEN = re.compile(r"\b(cancel+ation|cancel+ed|cancel|regret|award(ed)?|notification of|withdraw)", re.I)


def _d(s):
    m = re.match(r"(20\d\d-\d\d-\d\d)", str(s or ""))
    return m.group(1) if m else ""


def parse(js, fetched):
    rows, cut = [], str(dt.date.fromisoformat(fetched) - dt.timedelta(days=365))
    for r in js or []:
        if str(r.get("PUBLISH", "Y")).upper() != "Y":
            continue
        tid, ref = r.get("TENDER_ID"), clean(r.get("REFERENCE") or "")
        head = clean(r.get("HEADER_DESC") or r.get("SUMMARY") or "")
        if not tid or not head or NOT_OPEN.search(head + " " + ref):
            continue
        pub = _d(r.get("PUBLISHEDDATE"))
        if pub and pub < cut:
            continue
        div = clean(r.get("DESCRIPTION") or "")
        sector, how = classify(head)
        rows.append({"id": f"ESKOM-{tid}", "source": "Eskom Tender Bulletin (South Africa)", "group": "", "sector": sector, "nature": "",
                     "cpv": "", "classification": how, "country": "ZAF",
                     "buyer": "Eskom Holdings SOC Ltd" + (f" - {div.title()}" if div else ""),
                     "title": (f"{ref}: " if ref else "") + head[:280],
                     "notice_type": "Tender" + (" (e-tendering)" if r.get("E_TENDERING") else ""), "stage": "tender",
                     "access": clean(f"{r.get('Audience') or 'All suppliers'}; CSD registration needed to bid on etendering.eskom.co.za"),
                     "published": pub, "deadline": _d(r.get("CLOSING_DATE")), "value": "", "currency": "",
                     "link": f"https://tenderbulletin.eskom.co.za/tender/{tid}", "source_url": "https://tenderbulletin.eskom.co.za/",
                     "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def fetch():
    s = session()
    r = s.get(URL, timeout=90, headers={"Accept": "application/json"})
    r.raise_for_status()
    t = str(today())
    rows, q = quarantine_future(parse(r.json(), t), "eskom")
    rows = [x for x in rows if x["deadline"] and x["deadline"] >= t]
    keep, _ = rolling("eskom", rows)
    log.info("Eskom: %d open with a future closing date, %d kept, %d quarantined", len(rows), len(keep), q)
    return keep, {"new": len(rows), "quarantined": q}
