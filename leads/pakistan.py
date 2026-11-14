"""Pakistan: federal tenders on the PPRA e-Publish & Monitoring System (epms.ppra.gov.pk), public list "Active
Tenders" (open tenders plus those closed in the last 10 days): tender number, title, category, status, advertised
and closing date, organisation, detail page link.

Access (checked 2026-11-14): public HTML, no sign-in, no CAPTCHA; robots.txt absent (404). 1,815 listed on 14 Nov
2026 in pages of 50; read politely, 2 s apart. OPEN = status Published with a closing date today or later.
Disposals (sales by the government, e-auctions) are labelled and kept out of the open-tender count."""
import datetime as dt
import html
import re
import time

from .common import clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

BASE = "https://epms.ppra.gov.pk"
LIST = BASE + "/public/tenders/active-tenders?page={}"
MAX_PAGES = 80
MAIN = re.compile(r'<tr class="cb-rt-main">(.*?)</tr>', re.S)
DETAIL = re.compile(r'<tr class="cb-rt-detail" id="cb-rt-detail-(\d+)">(.*?)</tr>', re.S)
CELL = re.compile(r'<td[^>]*data-label="([^"]+)"[^>]*>(.*?)</td>', re.S)


def _txt(s):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))


def _date(s):
    m = re.search(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", s or "")
    if not m:
        return ""
    try:
        return str(dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date())
    except ValueError:
        return ""


def parse(page, fetched):
    details = {i: body for i, body in DETAIL.findall(page)}
    rows = []
    for tr in MAIN.findall(page):
        c = {k: v for k, v in CELL.findall(tr)}
        did = re.search(r'data-id="(\d+)"', tr)
        link = re.search(r'href="(https://epms\.ppra\.gov\.pk/public/tenders/tender-details/([\w-]+))"', c.get("Actions", ""))
        title = re.search(r"<strong>(.*?)</strong>", c.get("Tender Details", ""), re.S)
        if not link or not title:
            continue
        no, title = link.group(2), _txt(title.group(1))
        kind = _txt(re.search(r'class="badge bg-primary">(.*?)<', c.get("Tender No", ""), re.S).group(1)) if 'class="badge bg-primary"' in c.get("Tender No", "") else ""
        status = _txt(c.get("Status", ""))
        det = details.get(did.group(1) if did else "", "")
        org = re.search(r'Organization</span>.*?<strong>(.*?)</strong>', det, re.S)
        place = re.search(r'ri-map-pin-line"></i>(.*?)</small>', det, re.S)
        cat = re.search(r'Procurement Category</span>.*?class="cb-rt-dv">(.*?)</span>\s*</div>', det, re.S)
        disposal = kind.lower().startswith("disposal")
        sector, how = classify(title)
        rows.append({"id": "PK-PPRA-" + no, "source": "PPRA EPMS (Pakistan)", "group": "", "sector": sector, "nature": "",
                     "cpv": "", "classification": how, "country": "PAK",
                     "buyer": (_txt(org.group(1)) if org else "Federal government of Pakistan")[:120],
                     "title": title[:300], "notice_type": (kind or "Tender") + (" (corrigendum)" if "corrigendum" in status.lower() else "") + (" | " + _txt(cat.group(1)) if cat else "")
                     + (" | " + _txt(place.group(1)) if place else ""),
                     "stage": "disposal" if disposal else ("tender" if status.lower().startswith("published") or not status else status.lower()),
                     "access": "Pakistan federal procurement (international bidders where the notice says so)",
                     "published": _date(c.get("Advertised", "")), "deadline": _date(c.get("Closing", "")),
                     "deadline_basis": "submission", "value": "", "currency": "", "link": link.group(1),
                     "source_url": BASE + "/public/tenders/active-tenders", "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def fetch():
    s, t = session(), str(today())
    out, total, pages = [], 0, 0
    for p in range(1, MAX_PAGES + 1):
        r = s.get(LIST.format(p), timeout=60)
        r.raise_for_status()
        pages += 1
        if p == 1:
            m = re.search(r"Showing \d+ of ([\d,]+) tenders", r.text)
            total = int(m.group(1).replace(",", "")) if m else 0
        got = parse(r.text, t)
        if not got:
            break
        out += got
        if p * 50 >= total:
            break
        time.sleep(2)
    if not out:
        raise RuntimeError("Pakistan PPRA: no rows read; previous snapshot kept")
    out, q = quarantine_future(out, "pakistan")
    listed = len(out)
    out = [x for x in out if x["deadline"] >= t and x["stage"] in ("tender", "disposal")]
    keep, _ = snapshot("pakistan", list({x["id"]: x for x in out}.values()))
    log.info("Pakistan PPRA: %d open kept (%d disposals) of %d read, %d listed, %d pages", len(keep),
             sum(1 for x in keep if x["stage"] == "disposal"), listed, total, pages)
    return keep, {"new": len(keep), "listed": total, "pages": pages, "quarantined": q,
                  "complete_snapshot": 1 if total and listed >= 0.9 * total else 0}
