"""Japan - 官公需情報ポータルサイト (KKJ, the public-procurement portal run for the Small and Medium Enterprise Agency):
one public search API over tender notices of national agencies, prefectures and municipalities
(https://www.kkj.go.jp/api/, spec https://www.kkj.go.jp/doc/ja/api_guide.pdf). XML; up to 1,000 results per call, no
paging, so the collector splits by prefecture (LgCode 01-47), category (1 goods, 2 works, 3 services) and, where a
slice still has more than 1,000 hits, by halves of the bid-opening date window.

Notices published in the last 75 days are read. OPEN = a bid-opening date (OpeningTendersEvent) today or later;
failing that, the tender-submission date; failing both (most notices), a date written after a deadline or bid-date
word in the notice text (令和 era or western year). A notice with no such date is not counted (owner rule, 13 Nov). Titles are Japanese (lang ja).
Access (checked 2026-11-13 from the server): public API, no key, no sign-in. Gentle pacing (0.4 s between calls)."""
import datetime as dt
import re
import time
import xml.etree.ElementTree as ET

from .common import clean, log, quarantine_future, rolling, session, today, valid_date
from .sectors import classify

API = "https://www.kkj.go.jp/api/"
CAT = {"1": "goods", "2": "works", "3": "services"}
LOOKBACK_DAYS = 75     # notices published in the last 75 days; open = a future bid date
BUDGET_S = 1500


def _d(s):
    return valid_date(s)


FW = str.maketrans("０１２３４５６７８９", "0123456789")
# a date written after a deadline / bid-date word in the notice text: 令和８年１２月２３日 or 2026年12月23日
DUE_WORD = re.compile(r"(入札日時|入札書の提出期限|提出期限|受領期限|締切|締め切り|開札日時|開札の日時|入札期限|申請期限|参加申請|入札及び開札)")
DATE_JA = re.compile(r"(令和|R)\s*(\d{1,2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日|(20\d\d)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def text_deadline(desc, today):
    """Latest date that follows a deadline / bid-date word within 60 characters, if it is today or later
    (the bid / opening date, not the earlier participation-application date)."""
    t = (desc or "").translate(FW)
    best = None
    for m in DUE_WORD.finditer(t):
        for d in DATE_JA.finditer(t[m.end():m.end() + 60]):
            try:
                y = 2018 + int(d.group(2)) if d.group(1) else int(d.group(5))
                mo, da = (int(d.group(3)), int(d.group(4))) if d.group(1) else (int(d.group(6)), int(d.group(7)))
                v = dt.date(y, mo, da)
            except (TypeError, ValueError):
                continue
            if v >= today and (best is None or v > best):
                best = v
            break
    return str(best) if best else ""


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
        in_text = "" if (opening or submit) else text_deadline(g("ProjectDescription"), dt.date.fromisoformat(fetched))
        org, pref = g("OrganizationName"), g("PrefectureName")
        cat = g("Category")
        sector, how = classify(name)
        rows.append({"id": "KKJ-" + re.sub(r"[^A-Za-z0-9]", "", key)[:60], "source": "KKJ Japan public procurement portal", "group": "",
                     "sector": sector, "nature": {"物品": "supplies", "工事": "works", "役務": "services"}.get(cat, ""), "cpv": "",
                     "classification": how, "country": "JPN", "buyer": (org + (f" ({pref})" if pref and pref not in org else ""))[:120],
                     "title": name[:300], "notice_type": g("ProcedureType") or "公告", "stage": "tender",
                     "access": "Japanese government bidding qualification (全省庁統一資格 or local) usually required" +
                               (f"; grade {g('Certification')}" if g("Certification") else ""),
                     "published": _d(g("CftIssueDate")), "deadline": opening or submit or in_text, "value": "", "currency": "",
                     "link": g("ExternalDocumentURI") or "https://www.kkj.go.jp/", "source_url": "https://www.kkj.go.jp/",
                     "fetched": fetched, "contact": "", "lang": "ja"})
    return rows, hits


def _slice(s, lg, cat, lo, hi, fetched, out, stats, t0):
    if time.time() - t0 > BUDGET_S:
        stats["budget_stop"] = 1
        return
    params = {"Query": "入札", "LG_Code": f"{lg:02d}", "Category": cat, "Count": 1000,
              "CFT_Issue_Date": f"{lo.isoformat()}/{hi.isoformat()}"}
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
            _slice(s, lg, cat, t - dt.timedelta(days=LOOKBACK_DAYS), t, fetched, out, stats, t0)
    rows, q = quarantine_future(list(out.values()), "kkj")
    rows = [x for x in rows if x["deadline"] and x["deadline"] >= fetched]
    keep, _ = rolling("kkj", rows)
    log.info("KKJ Japan: %d open (future bid-opening or submission date), %d kept, %d quarantined; calls %s, errors %s, truncated %s%s",
             len(rows), len(keep), q, stats.get("calls", 0), stats.get("errors", 0), stats.get("truncated", 0),
             ", stopped at time budget" if stats.get("budget_stop") else "")
    return keep, {"new": len(rows), "quarantined": q, **stats}
