"""Dubai Electricity and Water Authority (DEWA, state utility): the public "Open Tenders" list
(https://www.dewa.gov.ae/en/supplier/services/list-of-tender-documents): tender number, title, status, tender fee,
floating (publication) date and closing date. One page holds the whole list (42 tenders on 12 Nov 2026).

Access (checked 2026-11-12): the page refuses the runner's address with a bot challenge (HTTP 403); it is read
through the regional relay (method: relay). robots.txt allows this path (only /sitecore, /gbill and a few pages are
disallowed); no terms-of-use page restricting automated reading was found. One request per run.
Bidding needs DEWA SRM registration (data/registry/registrations.csv); reading the list does not."""
import datetime as dt
import html
import re

from .common import clean, log, quarantine_future, rolling, session, today
from .sectors import classify

URL = "https://www.dewa.gov.ae/en/supplier/services/list-of-tender-documents"
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
PAIR = re.compile(r'<dt class="tender-result__key">(.*?)</dt>\s*<dd class="tender-result__value">(.*?)</dd>', re.S)


def _txt(x):
    return clean(html.unescape(re.sub(r"<input[^>]*>|<a[^>]*>View Advertisement</a>|<[^>]+>", " ", x)))


def _date(s):
    try:
        return str(dt.datetime.strptime(s.strip(), "%d-%b-%Y").date())
    except ValueError:
        return ""


def parse(body, fetched):
    rows = []
    for b in body.split('<div class="tender-result">')[1:]:
        f = {re.sub(r"[^a-z ]", "", _txt(k).lower()).strip(): _txt(v) for k, v in PAIR.findall(b)}
        no = re.sub(r"\D", "", f.get("tender no", ""))
        title = f.get("name of tenderer", "")
        status = f.get("tender status", "")
        if not no or not title or status.lower().startswith("closed"):
            continue
        fee = re.sub(r"[^\d.]", "", next((v for k, v in f.items() if k.startswith("tender fee")), ""))
        sector, how = classify(title)
        rows.append({"id": f"DEWA-{no}", "source": "DEWA (Dubai Electricity and Water Authority)", "group": "", "sector": sector, "nature": "",
                     "cpv": "", "classification": how, "country": "ARE", "buyer": "Dubai Electricity and Water Authority (DEWA)",
                     "title": title[:300], "notice_type": f"Open tender ({status})" if status else "Open tender", "stage": "tender",
                     "access": "Registered DEWA suppliers (SRM); tender fee " + (f"AED {fee}" if fee else "n/a"),
                     "published": _date(f.get("floating date", "")), "deadline": _date(f.get("closing date", "")), "value": "", "currency": "",
                     "link": URL, "source_url": URL, "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def fetch():
    s = session()
    s.headers["User-Agent"] = UA
    r = s.get(URL, timeout=60)   # leads.common session: falls back to the regional relay on HTTP 403
    r.raise_for_status()
    t = str(today())
    rows, q = quarantine_future(parse(r.text, t), "dewa")
    rows = [x for x in rows if not x["deadline"] or x["deadline"] >= t]
    keep, _ = rolling("dewa", rows)
    log.info("DEWA: %d open on the list, %d kept, %d quarantined", len(rows), len(keep), q)
    return keep, {"new": len(rows), "quarantined": q}
