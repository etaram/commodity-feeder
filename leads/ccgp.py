"""China Government Procurement Network (ccgp.gov.cn, Ministry of Finance): public tender announcements (公开招标公告)
of central government buyers (中央公告) and of provincial and local governments (地方公告): title, buyer, province,
publication time and link, newest first, 20 per page.

Access (checked 2026-11-12): plain HTTP from the runner (method: http); robots.txt absent (404); no terms-of-use page
found, footer "© 中华人民共和国财政部 版权所有" only. These are statutory public notices; we keep facts (title, buyer,
province, date, link) and link back. Polite: 2 s between pages, stops at notices older than DAYS.
Deadlines are inside each notice, not on the list: notices are kept 30 days from publication."""
import datetime as dt
import html
import re

from .common import clean, log, polite, quarantine_future, rolling, today
from .sectors import classify

BASE = "https://www.ccgp.gov.cn/cggg"
LISTS = {"zygg/gkzb": ("central", 10), "dfgg/gkzb": ("local", 30)}   # path -> (level, max pages)
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
DAYS = 7
LI = re.compile(r'<li>\s*<a href="\./([^"]+)"[^>]*title="([^"]+)"[^>]*>.*?</a>\s*发布时间：<em>(\d{4}-\d\d-\d\d)[^<]*</em>\s*地域：<em>([^<]*)</em>\s*采购人：<em>([^<]*)</em>', re.S)


def parse(body, path, fetched):
    level = LISTS.get(path, ("", 0))[0]
    out = []
    for href, title, date, prov, buyer in LI.findall(body):
        title = clean(html.unescape(title))
        sector, how = classify(title)
        out.append({"id": "CCGP-" + re.sub(r"\D", "", href.split("/")[-1])[-12:], "source": "China Government Procurement (CCGP)", "group": "",
                    "sector": sector, "nature": "", "cpv": "", "classification": how, "country": "CHN", "buyer": clean(html.unescape(buyer), 120),
                    "title": title[:300], "notice_type": "公开招标公告 (open tender)", "stage": "tender",
                    "access": "Open tender (Chinese government procurement law; domestic goods preference)", "published": date, "deadline": "",
                    "value": "", "currency": "", "link": f"{BASE}/{path}/{href}", "source_url": f"{BASE}/{path}/", "fetched": fetched,
                    "contact": "", "lang": "zh", "province": clean(prov, 30), "gov_level": level})
    return out


def fetch():
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5"})
    t = today(); cut = str(t - dt.timedelta(days=DAYS)); new, pages = [], 0
    for path, (level, max_pages) in LISTS.items():
        for page in range(max_pages):
            url = f"{BASE}/{path}/index.htm" if page == 0 else f"{BASE}/{path}/index_{page}.htm"
            r = s.get(url, timeout=40)
            pages += 1
            if r.status_code != 200:
                log.warning("CCGP %s page %d: HTTP %s", path, page, r.status_code); break
            r.encoding = "utf-8"
            rows = parse(r.text, path, str(t))
            new += [x for x in rows if x["published"] >= cut]
            polite(2)
            if not rows or min(x["published"] for x in rows) < cut:
                break
    new, q = quarantine_future(new, "ccgp")
    keep, _ = rolling("ccgp", new, max_age_days=30)
    log.info("CCGP: %d open-tender notices in %d days (%d pages; central %d, local %d), %d kept", len(new), DAYS, pages,
             sum(1 for x in new if x["gov_level"] == "central"), sum(1 for x in new if x["gov_level"] == "local"), len(keep))
    return keep, {"new": len(new), "pages": pages}
