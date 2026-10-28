"""EBRD procurement notices (ECEPP public search page): all open tenders; sector by keyword."""
import datetime as dt
import html
import re

from .common import cffi_get, clean, log, today
from .sectors import classify
from .taxonomy import group_of_text

URL = "https://ecepp.ebrd.com/delta/noticeSearchResults.html"
OPEN = ("Invitation For Tenders", "Invitation for Prequalification", "Invitation For Expression of Interest",
        "Request for Quotations")


def _d(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def fetch():
    r = cffi_get(URL)
    if r.status_code != 200:
        log.warning("EBRD %s", r.status_code); return [], {}
    rows, t = [], today()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
        link = re.search(r'href="(viewNotice\.html\?displayNoticeId=\d+)"', tr)
        cells = [clean(html.unescape(re.sub(r"<[^>]+>", " ", c))) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        text = " | ".join(c for c in cells if c)
        if not link or not any(o.lower() in text.lower() for o in OPEN):
            continue
        meta = re.search(r"\[(.*?)\]", text)
        meta = meta.group(1) if meta else ""
        title = cells[0] if cells else ""
        low = (title + " " + meta).lower()
        gid = group_of_text(title) if "Goods" in meta else None
        sector, method = classify(title)
        dates = [d for d in (_d(c) for c in cells) if d]
        dl = max(dates) if dates else None
        if dl and dl < t:
            continue
        parts = [p.strip() for p in meta.split(",")]
        rows.append({
            "id": f"EBRD-{link.group(1).split('=')[-1]}", "source": "EBRD", "group": gid or "", "sector": sector, "stage": "tender",
            "nature": "goods" if "Goods" in meta else "works" if "Works" in meta else "services" if "Consult" in meta or "Services" in meta else "",
            "access": "International (EBRD rules)", "lang": "",
            "country": title.split(":")[0][:40], "buyer": clean(parts[-3] if len(parts) >= 3 else "", 120),
            "title": title[:300], "classification": "keyword", "notice_type": next((o for o in OPEN if o.lower() in text.lower()), ""),
            "published": str(min(dates) if dates else ""), "deadline": str(dl or ""), "value": "", "currency": "",
            "link": "https://ecepp.ebrd.com/delta/" + link.group(1), "contact": "", "match": "",
        })
    log.info("EBRD rows %d", len(rows))
    return rows, {}
