"""New Zealand - GETS (Government Electronic Tenders Service, gets.govt.nz), the public list of open notices.
Reads the public external index (all pages, sorted by close date). Rolling store."""
import datetime as dt
import html
import re

from .common import clean, log, polite, rolling, session, today
from .sectors import classify

BASE = "https://www.gets.govt.nz/"
ROW = re.compile(r'<tr id="tender-(\d+)"[^>]*>(.*?)</tr>', re.S)
TYPES = {"RFT": "Request for Tenders", "RFP": "Request for Proposals", "RFQ": "Request for Quotes", "RFI": "Request for Information",
         "EOI": "Expression of Interest", "ROI": "Registration of Interest", "AOI": "Advance Notice"}


def _date(txt):
    m = re.search(r"(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})", txt)
    if not m:
        return ""
    try:
        return dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y").date().isoformat()
    except ValueError:
        return ""


def fetch():
    s, t = session(), today()
    new, seen = [], set()
    for page in range(1, 40):
        try:
            r = s.get(BASE + "ExternalIndex.htm", params={"page": page, "orderBy": "date"}, timeout=60)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            log.warning("GETS page %d: %s", page, str(e)[:120]); break
        rows = ROW.findall(r.text)
        if not rows:
            break
        fresh = 0
        for tid, body in rows:
            if tid in seen:
                continue
            seen.add(tid); fresh += 1
            tds = re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)
            if len(tds) < 6:
                continue
            txt = [clean(html.unescape(re.sub(r"<[^>]+>", " ", x))) for x in tds]
            href = re.search(r'href="([^"]+)"', tds[0])
            code = re.search(r"<abbr[^>]*>(.*?)</abbr>", tds[3], re.S)
            kind = clean(code.group(1)) if code else txt[3]
            dl = _date(txt[4])
            if dl and dl < str(t):
                continue
            sector, method = classify(txt[2])
            new.append({
                "id": "NZ-" + tid, "source": "GETS NZ", "group": "", "sector": sector, "nature": "", "cpv": "", "classification": method,
                "country": "NZL", "buyer": txt[5], "title": txt[2][:300], "notice_type": TYPES.get(kind, kind), "stage": "tender",
                "access": "Open (New Zealand Government Procurement Rules; overseas suppliers may respond)",
                "published": str(t), "deadline": dl, "value": "", "currency": "",
                "link": BASE + (href.group(1) if href else f"ExternalTenderDetails.htm?id={tid}"), "contact": "", "lang": "",
            })
        if not fresh:
            break
        polite(1)
    rows, _ = rolling("gets", new)
    log.info("GETS new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
