"""Japan - 官公需情報ポータルサイト (KKJ, the public-procurement portal run for the Small and Medium Enterprise Agency):
one public search API over tender notices of national agencies, prefectures and municipalities
(https://www.kkj.go.jp/api/, spec https://www.kkj.go.jp/doc/ja/api_guide.pdf). XML; up to 1,000 results per call, no
paging, so the collector splits by prefecture (LgCode 01-47), category (1 goods, 2 works, 3 services) and, where a
slice still has more than 1,000 hits, by halves of the bid-opening date window.

OPEN = a bid-opening date (OpeningTendersEvent) today or later; failing that, the tender-submission date. A notice
with neither is not counted (owner rule, 13 Nov). Titles are Japanese (lang ja).
Access (checked 2026-11-13 from the server): public API, no key, no sign-in. Gentle pacing (0.4 s between calls)."""
import datetime as dt
import re
import time
import xml.etree.ElementTree as ET

from .common import clean, log, quarantine_future, rolling, session, today
from .sectors import classify

API = "https://www.kkj.go.jp/api/"
CAT = {"1": "goods", "2": "works", "3": "services"}
HORIZON_DAYS = 240
BUDGET_S = 1500


def _d(s):
    m = re.match(r"(20\d\d-\d\d-\d\d)", str(s or ""))
    return m.group(1) if m else ""


def parse(xml_text, fetched):
    root = ET.fromstring(xml_text)
    hits = int(root.findtext(".//SearchHits") or 0)
    rows = []
    for r in root.iter("SearchResult"):
        g = lambda k: clean(r.findtext(k) or "")   # noqa: E731
        key, name = g("Key"), g("ProjectName")
        if not key or not name:
            continue
        opening, submit = _d(g("OpeningTendersEvent")), _d(g("TenderSubmissionDeadline"))
        org, pref = g("OrganizationName"), g("PrefectureName")
        cat = g("Category")
        sector, how = classify(name)
        rows.append({"id": "KKJ-" + re.sub(r"[^A-Za-z0-9]", "", key)[:60], "source": "KKJ Japan public procurement portal", "group": "",
                     "sector": sector, "nature": {"物品": "supplies", "工事": "works", "役務": "services"}.get(cat, ""), "cpv": "",
                     "classification": how, "country": "JPN", "buyer": (org + (f" ({pref})" if pref and pref not in org else ""))[:120],
                     "title": name[:300], "notice_type": g("ProcedureType") or "公告", "stage": "tender",
                     "access": "Japanese government bidding qualification (全省庁統一資格 or local) usually required" +
                               (f"; grade {g('Certification')}" if g("Certification") else ""),
                     "published": _d(g("CftIssueDate")), "deadline": opening or submit, "value": "", "currency": "",
                     "link": g("ExternalDocumentURI") or "https://www.kkj.go.jp/", "source_url": "https://www.kkj.go.jp/",
                     "fetched": fetched, "contact": "", "lang": "ja"})
    return rows, hits


def _slice(s, lg, cat, lo, hi, fetched, out, stats, t0):
    if time.time() - t0 > BUDGET_S:
        stats["budget_stop"] = 1
        return
    params = {"Query": "入札", "LG_Code": f"{lg:02d}", "Category": cat, "Count": 1000,
              "Opening_Tenders_Event": f"{lo.isoformat()}/{hi.isoformat()}"}
    try:
        r = s.get(API, params=params, timeout=60)
        r.raise_for_status()
        rows, hits = parse(r.text, fetched)
    except Exception as e:  # noqa: BLE001
        stats["errors"] = stats.get("errors", 0) + 1
        log.warning("KKJ %02d/%s %s..%s: %s", lg, cat, lo, hi, type(e).__name__)
        return
    stats["calls"] = stats.get("calls", 0) + 1
    time.sleep(0.4)
    if hits > len(rows) and hi > lo:
        mid = lo + (hi - lo) // 2
        _slice(s, lg, cat, lo, mid, fetched, out, stats, t0)
        _slice(s, lg, cat, mid + dt.timedelta(days=1), hi, fetched, out, stats, t0)
        return
    if hits > len(rows):
        stats["truncated"] = stats.get("truncated", 0) + (hits - len(rows))
    for x in rows:
        out[x["id"]] = x


def fetch():
    t = today()
    fetched = str(t)
    s = session()
    out, stats, t0 = {}, {}, time.time()
    for lg in range(1, 48):
        for cat in CAT:
            _slice(s, lg, cat, t, t + dt.timedelta(days=HORIZON_DAYS), fetched, out, stats, t0)
    rows, q = quarantine_future(list(out.values()), "kkj")
    rows = [x for x in rows if x["deadline"] and x["deadline"] >= fetched]
    keep, _ = rolling("kkj", rows)
    log.info("KKJ Japan: %d open (future bid-opening or submission date), %d kept, %d quarantined; calls %s, errors %s, truncated %s%s",
             len(rows), len(keep), q, stats.get("calls", 0), stats.get("errors", 0), stats.get("truncated", 0),
             ", stopped at time budget" if stats.get("budget_stop") else "")
    return keep, {"new": len(rows), "quarantined": q, **stats}
