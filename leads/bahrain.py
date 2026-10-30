"""Bahrain: Tender Board e-tendering public dashboard (published tenders with time left). Needs a real browser."""
import datetime as dt
import html as H
import re

from .common import clean, log, rolling, today
from .sectors import classify
from .stealth import html

URL = "https://etendering.tenderboard.gov.bh/Tenders/publicDash?CTRL_STRDIRECTION=LTR"


def fetch():
    t, new = today(), []
    b = html(URL)
    for tr in re.findall(r"<tr><td class=\"table_td\">(.*?)</tr>", b, flags=re.S):
        m = re.search(r"getNit\('(\d+)'\)[^>]*>([^<]*)</span>.*?data-original-title=\"([^\"]*)\"", tr, flags=re.S)
        if not m:
            continue
        nit, ref, title = m.group(1), H.unescape(m.group(2)).strip(" ."), clean(H.unescape(m.group(3)))
        tds = re.findall(r"<td class=\"table_td[^\"]*\">(.*?)</td>", tr, flags=re.S)
        ent = clean(H.unescape(re.search(r"data-original-title=\"([^\"]*)\"", tds[0]).group(1))) if tds and re.search(r"data-original-title", tds[0]) else "Bahrain Tender Board"
        left = re.search(r"(\d+)\s*Days?", re.sub(r"<[^>]+>", " ", tr[tr.rfind("table_td"):]))
        close = (t + dt.timedelta(days=int(left.group(1)))) if left else None
        sector, _ = classify(title)
        new.append({"id": f"BH-{nit}", "source": "Tender Board (Bahrain)", "group": "", "sector": sector, "nature": "", "cpv": "", "classification": ref,
                    "country": "BHR", "buyer": ent[:120], "title": title[:300], "notice_type": "Public tender", "stage": "tender",
                    "access": "National (foreign firms may bid)", "published": "", "deadline": str(close or ""), "value": "", "currency": "",
                    "link": URL, "contact": "", "lang": "en"})
    rows, _ = rolling("bahrain", new)
    log.info("Bahrain new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
