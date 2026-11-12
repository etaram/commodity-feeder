"""China Southern Power Grid (CSG, state-owned grid of five southern provinces): tender announcements (招标公告) on its
supply-chain platform https://www.bidding.csg.cn/zbgg/index.jhtml - buyer (the CSG company running the tender),
title, publication date and link, newest first, 10 per page.

Access (checked 2026-11-12): plain HTTP from the runner (method: http); no robots.txt on the host (404); the footer
links "法律声明" and "服务条款" are empty ("###"), so no terms text could be read - only a copyright line
(中国南方电网有限责任公司版权所有). We keep facts (title, buyer, date, link) and link back; no document text is copied.
Polite: 2 s between pages, stops at notices older than DAYS. Full documents and bidding need CSG supplier
registration (data/registry/registrations.csv)."""
import datetime as dt
import html
import re

from .common import clean, log, polite, quarantine_future, rolling, today
from .sectors import classify

BASE = "https://www.bidding.csg.cn"
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
DAYS, MAX_PAGES = 7, 40
LI = re.compile(r'<li><span class="Right">.*?<span class="Black14 Gray">(\d{4}-\d\d-\d\d)</span></span>.*?<a class="Blue">(.*?)</a>.*?<a href="(/zbgg/\d+\.jhtml)"[^>]*>(.*?)</a></li>', re.S)


def parse(body, fetched):
    out = []
    for date, buyer, href, title in LI.findall(body):
        title = clean(html.unescape(re.sub(r"<[^>]+>", "", title)))
        sector, how = classify(title)
        out.append({"id": "CSG-" + re.sub(r"\D", "", href), "source": "China Southern Power Grid (CSG) bidding", "group": "", "sector": sector,
                    "nature": "", "cpv": "", "classification": how, "country": "CHN", "buyer": clean(html.unescape(buyer), 120),
                    "title": title[:300], "notice_type": "招标公告 (tender notice)", "stage": "tender",
                    "access": "Registered CSG suppliers (domestic qualification usually required)", "published": date, "deadline": "",
                    "value": "", "currency": "", "link": BASE + href, "source_url": BASE + "/zbgg/index.jhtml", "fetched": fetched,
                    "contact": "", "lang": "zh"})
    return out


def fetch():
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5"})
    t = today(); cut = str(t - dt.timedelta(days=DAYS)); new = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE}/zbgg/index.jhtml" if page == 1 else f"{BASE}/zbgg/index_{page}.jhtml"
        r = s.get(url, timeout=40)
        if r.status_code != 200:
            log.warning("CSG page %d: HTTP %s", page, r.status_code); break
        r.encoding = "utf-8"
        rows = parse(r.text, str(t))
        new += [x for x in rows if x["published"] >= cut]
        if not rows or min(x["published"] for x in rows) < cut:
            break
        polite(2)
    new, q = quarantine_future(new, "csg")
    keep, _ = rolling("csg", new, max_age_days=30)
    log.info("CSG: %d notices in the last %d days (%d pages), %d kept, %d quarantined", len(new), DAYS, page, len(keep), q)
    return keep, {"new": len(new), "pages": page}
