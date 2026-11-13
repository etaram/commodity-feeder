"""Philippines: PhilGEPS open opportunities (all government agencies, ~17k open at a time, mostly small local buys).
Reads the newest pages each run (ASP.NET paging); the rolling cache keeps earlier ones until their closing date."""
import datetime as dt
import html
import re
import time

from .common import clean, log, polite, rolling, today
from .sectors import classify

BASE = "https://notices.philgeps.gov.ph/GEPSNONPILOT/Tender/"
URL = BASE + "SplashOpportunitiesSearchUI.aspx?menuIndex=3&ClickFrom=OpenOpp&Result=3"
ROW = re.compile(r'<td[^>]*>(\d\d/\d\d/\d{4})</td><td[^>]*>(\d\d/\d\d/\d{4})[^<]*</td><td class="GridItemTD">\s*'
                 r'<a [^>]*href="SplashBidNoticeAbstractUI\.aspx\?menuIndex=3&amp;refID=(\d+)&amp;Result=3">([^<]+)</a>\s*'
                 r'<span [^>]*>([^<]*)</span>', re.S)
PAGES = 900   # ~17k open notices at a time, 20 per page; time budget below
BUDGET_S = 900


def _d(s):
    try:
        return dt.datetime.strptime(s, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ""


def _form(body):
    return {k: html.unescape(v) for k, v in re.findall(r'<input type="hidden" name="(__[A-Z]+)" id="[^"]*" value="([^"]*)"', body)}


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    t, new, seen = str(today()), [], set()
    t0 = time.time()
    page = 1
    try:
        r = s.get(URL, timeout=60)
    except Exception as e:  # noqa: BLE001
        log.warning("PhilGEPS: %s", str(e)[:120])
        rows, _ = rolling("philippines", [])
        return rows, {"new": 0}
    while True:
        got = 0
        for pub, close, rid, title, extra in ROW.findall(r.text):
            if rid in seen:
                continue
            seen.add(rid); got += 1
            dl = _d(close)
            if dl and dl < t:
                continue
            m = re.match(r"\s*,\s*(.*?)\s+,(.*)$", html.unescape(extra), re.S)  # ", <category> ,<organisation>"
            cat, org = (clean(m.group(1)), clean(m.group(2))) if m else ("", clean(html.unescape(extra)).strip(", "))
            title = clean(html.unescape(title))
            sector, how = classify(f"{title} {cat}")
            new.append({
                "id": f"PH-{rid}", "source": "PhilGEPS (Philippines)", "group": "", "sector": sector, "nature": "",
                "cpv": "", "classification": how, "country": "PHL", "buyer": org[:120], "title": title[:300],
                "notice_type": cat[:60], "stage": "tender", "access": "Registered suppliers (PhilGEPS)",
                "published": _d(pub), "deadline": dl, "value": "", "currency": "PHP",
                "link": f"{BASE}SplashBidNoticeAbstractUI.aspx?menuIndex=3&refID={rid}&Result=3", "lang": "", "contact": "",
            })
        if got == 0 or page >= PAGES or time.time() - t0 > BUDGET_S:
            break
        f = _form(r.text)
        if "__VIEWSTATE" not in f:
            break
        f.update({"__EVENTTARGET": "pgCtrlDetailedSearch$nextLB", "__EVENTARGUMENT": ""})
        polite(1.2)
        try:
            r = s.post(URL, data=f, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("PhilGEPS page %d: %s", page + 1, str(e)[:120]); break
        page += 1
    rows, _ = rolling("philippines", new)
    log.info("Philippines new %d, open %d (pages %d)", len(new), len(rows), page)
    return rows, {"new": len(new)}
