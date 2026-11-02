"""Dubai: eSupply current opportunities (all Dubai government entities): buyer, title, publication and closing dates.
Many are small quotations; all are open to registered suppliers."""
import datetime as dt
import html
import re

from .common import clean, log, polite, rolling, today
from .sectors import classify

BASE = "https://esupply.dubai.gov.ae"
LIST = BASE + "/esop/toolkit/opportunity/current/list.si"
ROW = re.compile(r'<td class="col__fixed_">([A-Z]{3})</td>\s*<td class="col__fixed_">([^<]*)</td>\s*<td class="col__fixed_">'
                 r'<a [^>]*goToDetail\(&#39;(\d+)&#39;[^>]*title="View Details: ([^"]*)">.*?</a></td>\s*'
                 r'<td class="column-date col__fixed_">([^<]*)</td>\s*<td class="col__fixed_">([^<]*)</td>\s*'
                 r'<td class="column-date col__fixed_">([^<]*)</td>', re.S)


def _d(s):
    try:
        return dt.datetime.strptime(s.strip()[:10], "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ""


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    t, new, seen = str(today()), [], set()
    r = s.get(BASE + "/esop/guest/go/public/opportunity/current", timeout=60)
    for page in range(1, 15):
        if page > 1:
            r = s.post(LIST, data={"userAct": "changePage", "opportunityListManager.pagerComponent.page": page}, timeout=60)
        got = 0
        for cur, buyer, oid, title, pub, cat, close in ROW.findall(r.text):
            if oid in seen:
                continue
            seen.add(oid); got += 1
            dl = _d(close)
            if dl and dl < t:
                continue
            title = clean(html.unescape(title))
            sector, how = classify(title)
            new.append({
                "id": f"AEDXB-{oid}", "source": "eSupply (Dubai)", "group": "", "sector": sector, "nature": "", "cpv": "",
                "classification": how, "country": "ARE", "buyer": clean(html.unescape(buyer), 120), "title": title[:300],
                "notice_type": clean(cat, 60), "stage": "tender", "access": "Registered suppliers (eSupply)",
                "published": _d(pub), "deadline": dl, "value": "", "currency": cur,
                "link": f"{BASE}/esop/toolkit/opportunity/current/{oid}/detail.si", "lang": "", "contact": "",
            })
        if got == 0:
            break
        polite(1.5)
    rows, _ = rolling("dubai", new)
    log.info("Dubai new %d, open %d (pages %d)", len(new), len(rows), page)
    return rows, {"new": len(new)}
