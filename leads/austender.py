"""Australia: AusTender current Approaches to Market (public RSS feed)."""
import datetime as dt
import html
import re

from .common import clean, log, rolling, session, today
from .sectors import classify

URL = "https://www.tenders.gov.au/public_data/rss/rss.xml"


def _d(s):
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", s or "")
    return dt.datetime.strptime(m.group(0), "%d-%b-%Y").date() if m else None


def fetch():
    r = session().get(URL, timeout=90)
    t, new = today(), []
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        g = lambda tag: clean(html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(f"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1])))
        title, link, desc = g("title"), g("link"), re.sub(r"<[^>]+>", " ", g("description"))
        close = _d(re.search(r"Close Date[^:]*:\s*([^|<]+)", desc).group(1)) if "Close Date" in desc else None
        if close and close < t:
            continue
        agency = (re.search(r"Agency:\s*(.*?)(?:Category:|Close|$)", desc) or [None, ""])[1]
        cat = (re.search(r"Category:\s*(.*?)(?:Close|Agency|Description|$)", desc) or [None, ""])[1]
        sector, method = classify(f"{title} {cat}")
        new.append({
            "id": "AU-" + link.rsplit("/", 1)[-1], "source": "AusTender (Australia)", "group": "", "sector": sector,
            "nature": "", "cpv": "", "classification": clean(cat, 60) or method, "country": "AUS",
            "buyer": clean(agency, 120), "title": clean(f"{title} | {desc}", 300), "notice_type": "Approach to Market",
            "stage": "tender", "access": "GPA/FTA open", "published": "", "deadline": str(close or ""),
            "value": "", "currency": "", "link": link, "contact": "", "lang": "",
        })
    rows, _ = rolling("austender", new)
    log.info("AusTender new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
