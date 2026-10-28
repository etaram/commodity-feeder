"""Islamic Development Bank project procurement tenders (public listing, status=active)."""
import datetime as dt
import html
import re

from .common import cffi_get, clean, log, polite, rolling, today
from .regions import iso3
from .sectors import classify

URL = "https://www.isdb.org/project-procurement/tenders"


def _d(s):
    try:
        return dt.datetime.strptime(s.strip(), "%d %B %Y").date()
    except ValueError:
        return None


def fetch():
    t, new = today(), []
    for page in range(0, 6):
        r = cffi_get(f"{URL}?status=active&page={page}")
        if r.status_code != 200:
            log.warning("IsDB %s", r.status_code); break
        arts = re.findall(r'<article role="article" about="(/project-procurement/tenders/[^"]+)"(.*?)</article>', r.text, re.S)
        if not arts:
            break
        for url, a in arts:
            parts = [clean(html.unescape(p)) for p in re.split(r"<[^>]+>", a) if clean(p)]
            parts = [p for p in parts if not p.startswith("data-nid") and "class=" not in p]
            if len(parts) < 4 or "Closed" in parts[:3]:
                continue
            title = parts[0]; ttype = parts[2] if len(parts) > 2 else ""
            date = next((d for d in (_d(p) for p in parts) if d), None)
            if date and date < t:
                continue
            country = parts[3] if len(parts) > 3 else ""
            sector, method = classify(title)
            new.append({
                "id": "IsDB-" + url.rsplit("/", 1)[-1][:80], "source": "IsDB", "group": "", "sector": sector,
                "nature": "works" if "Civil Works" in ttype else "", "cpv": "", "classification": method,
                "country": iso3(country) or country, "buyer": "IsDB-financed project", "title": title[:300],
                "notice_type": ttype, "stage": "planned" if "General Procurement" in ttype else "tender",
                "access": "International (IsDB rules, member countries)", "published": "", "deadline": str(date or ""),
                "value": "", "currency": "", "link": "https://www.isdb.org" + url, "contact": "", "lang": "",
            })
        polite(1)
    rows, _ = rolling("isdb", new)
    log.info("IsDB new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
