"""European Dynamics e-procurement portals (Ghana GHANEPS, Zambia ZPPA): the live list of current calls for tenders
(title, procuring entity, deadline, procedure, status, publication date), newest first, read page by page until a
page holds nothing still open. (Their OCDS packages lag by months, so the live list is used instead.)"""
import datetime as dt
import html
import re

from .common import clean, log, polite, rolling, today
from .sectors import classify

PORTALS = {"ghana": ("https://www.ghaneps.gov.gh", "GHANEPS (Ghana)", "GH", "GHA"),
           "zambia": ("https://eprocure.zppa.org.zm", "ZPPA (Zambia)", "ZM", "ZMB")}
TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
INTL = re.compile(r"international|\bICB\b|\bITT\b", re.I)


def _txt(x):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", x)))


def _date(s):
    m = re.search(r"(\d\d)/(\d\d)/(\d{4})", s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def fetch_portal(key):
    from curl_cffi import requests as cr
    base, source, prefix, country = PORTALS[key]
    s = cr.Session(impersonate="chrome")
    t, new, seen, page, pid = str(today()), [], set(), 1, None
    while page <= 120:
        url = f"{base}/epps/viewCFTSAction.do?latest=true" + (f"&d-{pid}-p={page}" if pid else "")
        try:
            r = s.get(url, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("%s page %d: %s", key, page, str(e)[:120]); break
        if r.status_code != 200:
            log.warning("%s %s page %d", key, r.status_code, page); break
        body = r.text
        if pid is None:
            m = re.search(r"d-(\d+)-p=\d", body)
            pid = m.group(1) if m else None
        got = opened = 0
        for tr in TR.findall(body):
            m = re.search(r'resourceId=(\d+)">([^<]+)</a>', tr)
            tds = TD.findall(tr)
            if not m or len(tds) < 7 or m.group(1) in seen:
                continue
            seen.add(m.group(1)); got += 1
            rid, title = m.group(1), clean(html.unescape(m.group(2)))
            buyer, dl, proc, status, pub = _txt(tds[2]), _date(_txt(tds[4])), _txt(tds[5]), _txt(tds[6]), _date(_txt(tds[-1]))
            if (dl and dl < t) or not re.search(r"submission|clarif|open", status, re.I):
                continue
            opened += 1
            sector, how = classify(title)
            new.append({
                "id": f"{prefix}-{rid}", "source": source, "group": "", "sector": sector, "nature": "", "cpv": "",
                "classification": how, "country": country, "buyer": buyer[:120], "title": title[:300],
                "notice_type": proc[:60], "stage": "tender",
                "access": "International" if INTL.search(proc) else "National (foreign firms may bid)",
                "published": pub, "deadline": dl, "value": "", "currency": "",
                "link": f"{base}/epps/cft/prepareViewCfTWS.do?resourceId={rid}", "lang": "", "contact": "",
            })
        if got == 0 or not pid or (opened == 0 and page >= 5):
            break
        page += 1
        polite(1.2)
    rows, _ = rolling(key, new)
    log.info("%s new %d, open %d (pages %d)", key, len(new), len(rows), page)
    return rows, {"new": len(new)}
