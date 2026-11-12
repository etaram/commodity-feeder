"""Lebanon: Public Procurement Authority central platform (https://www.ppa.gov.lb/en/tenders): every announced
procurement of ministries, public institutions, water establishments and municipalities (local government) - id,
buyer, procurement code, title, method, announcement date, bid opening date. 50 per page, newest first.

Access (checked 2026-11-12): plain HTTP from the runner (method: http); robots.txt "User-agent: * Disallow:" (all
allowed); no terms-of-use page restricting reuse was found. Polite: 2 s between pages, stops at announcements older
than DAYS. Titles are mostly Arabic (lang ar)."""
import datetime as dt
import html
import re

from .common import clean, log, polite, quarantine_future, rolling, today
from .sectors import classify

BASE = "https://www.ppa.gov.lb/en/tenders"
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
DAYS, MAX_PAGES = 21, 8
TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
DATE = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})")
MONTHS = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September",
                                      "October", "November", "December"), 1)}


def _txt(x):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", x)))


def _date(x):
    m = DATE.search(_txt(x))
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m else ""


def parse(body, fetched):
    out = []
    for tr in TR.findall(body):
        tds = TD.findall(tr)
        if len(tds) < 7:
            continue
        nid, buyer, code, title, method = _txt(tds[0]), _txt(tds[1]), _txt(tds[2]), _txt(tds[3]), _txt(tds[4])
        m = re.search(r'href="([^"]+/tenders/details/\d+)"', tr)
        if not nid.isdigit() or not title:
            continue
        sector, how = classify(title)
        local = bool(re.search(r"municipalit|union of municipalities|بلدية|اتحاد بلديات", buyer, re.I))
        out.append({"id": f"LB-{nid}", "source": "PPA (Lebanon)", "group": "", "sector": sector, "nature": "", "cpv": "", "classification": how,
                    "country": "LBN", "buyer": buyer[:120], "title": title[:300], "notice_type": f"{method} ({code})" if code else method,
                    "stage": "tender", "access": "National (Public Procurement Law 244/2021; foreign bidders per tender file)",
                    "published": _date(tds[5]), "deadline": _date(tds[6]), "value": "", "currency": "", "link": m.group(1) if m else BASE,
                    "source_url": BASE, "fetched": fetched, "contact": "", "lang": "ar" if re.search(r"[؀-ۿ]", title) else "",
                    "gov_level": "local" if local else "national"})
    return out


def fetch():
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "en,ar;q=0.8"})
    t = today(); cut = str(t - dt.timedelta(days=DAYS)); new = []
    for page in range(1, MAX_PAGES + 1):
        r = s.get(BASE, params={"page": page} if page > 1 else None, timeout=60)
        if r.status_code != 200:
            log.warning("Lebanon page %d: HTTP %s", page, r.status_code); break
        r.encoding = "utf-8"
        rows = parse(r.text, str(t))
        new += [x for x in rows if (x["deadline"] or "9999") >= str(t)]
        if not rows or min((x["published"] or "9999") for x in rows) < cut:
            break
        polite(2)
    new, q = quarantine_future(new, "lebanon")
    keep, _ = rolling("lebanon", new)
    log.info("Lebanon PPA: %d open (%d pages, %d local government), %d kept", len(new), page, sum(1 for x in new if x["gov_level"] == "local"), len(keep))
    return keep, {"new": len(new), "pages": page}
