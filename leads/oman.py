"""Oman: Tender Board e-tendering public dashboard (new tenders). Arabic titles; sector by Arabic keyword."""
import datetime as dt
import html
import re

from .common import cffi_get, clean, log, rolling, today
from .etimad import _sector

URL = "https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=NewTenders"


def _d(s):
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", s or "")
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def fetch():
    r = cffi_get(URL)
    t, new = today(), []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
        cells = [clean(html.unescape(re.sub(r"<[^>]+>", " ", c))) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 6 or not re.match(r"^\d+\.?$", cells[0]):
            continue
        ref, title, entity, cat, ttype = cells[1], cells[2].rstrip(". "), cells[3], cells[4], cells[5]
        dates = " ".join(cells[6:8])
        close = _d((re.search(r"Bid Closing Date:\s*([\d-]+)", dates) or [None, ""])[1])
        if close and close < t:
            continue
        new.append({
            "id": f"OM-{re.sub(r'[^0-9A-Za-z]+', '', ref)[-30:] or ref}", "source": "Tender Board (Oman)", "group": "",
            "sector": _sector(title, entity, cat), "nature": "", "cpv": "", "classification": clean(cat, 60), "country": "OMN",
            "buyer": entity[:120], "title": f"{title} | {cat}"[:300], "notice_type": ttype[:60], "stage": "tender",
            "access": "International" if "International" in ttype else "National (local registration)",
            "published": "", "deadline": str(close or ""), "value": "", "currency": "", "lang": "ar",
            "link": "https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=NewTenders", "contact": "",
        })
    rows, _ = rolling("oman", new)
    log.info("Oman new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
