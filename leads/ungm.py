"""United Nations Global Marketplace (UNGM): active procurement notices of ~40 UN agencies (UNICEF, WFP, UNOPS,
UNHCR, FAO, WHO, UNFPA, IOM, ...). Public search endpoint, newest first; rolling cache keeps the open set."""
import datetime as dt
import html
import re

from .common import cache_empty, clean, log, polite, rolling, today
from .regions import iso3
from .sectors import classify

BASE = "https://www.ungm.org"
SKIP = re.compile(r"request for information|call for individual|individual consult", re.I)


def _d(s):
    m = re.search(r"(\d{2})-([A-Za-z]{3})-(\d{4})", s or "")
    return dt.datetime.strptime(m.group(0), "%d-%b-%Y").date() if m else None


def _txt(s):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", s)))


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    g = s.get(BASE + "/Public/Notice", timeout=60)
    tok = re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', g.text)
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/Public/Notice",
           "RequestVerificationToken": tok.group(1) if tok else ""}
    t = today()
    full = cache_empty("ungm")
    cut = t - dt.timedelta(days=400 if full else 5)
    new, page, total = [], 0, None
    while page < 200:
        body = {"PageIndex": page, "PageSize": 15, "Title": "", "Description": "", "Reference": "", "PublishedFrom": "",
                "PublishedTo": "", "DeadlineFrom": "", "DeadlineTo": "", "Countries": [], "Agencies": [], "UNSPSCs": [],
                "NoticeTypes": [], "SortField": "DatePublished", "SortAscending": False, "isPicker": False,
                "IsSustainable": False, "IsActive": True, "NoticeDisplayType": None,
                "NoticeSearchTotalLabelId": "noticeSearchTotal", "TypeOfCompetitions": []}
        r = s.post(BASE + "/Public/Notice/Search", json=body, headers=hdr, timeout=60)
        if r.status_code != 200:
            log.warning("UNGM %s page %d", r.status_code, page); break
        if total is None:
            m = re.search(r'noticeTotal = "(\d+)"', r.text); total = int(m.group(1)) if m else None
        rows = re.findall(r'data-noticeid="(\d+)"(.*?)(?=<div role="row"|\Z)', r.text, re.S)
        if not rows:
            break
        stop = False
        for nid, block in rows:
            cells = [_txt(c) for c in re.findall(r'<div role="cell"[^>]*>(.*?)</div>\s*(?=<div role="cell"|\Z)', block, re.S)]
            cells = [c for c in cells if c]
            if len(cells) < 6:
                continue
            ci = next((i for i, c in enumerate(cells) if _d(c)), None)
            if ci is None:
                continue
            title = re.sub(r"^\d+\s+", "", cells[ci - 1]) if ci else ""
            dl, pub = _d(cells[ci]), _d(cells[ci + 1]) if len(cells) > ci + 1 else None
            agency = cells[ci + 2] if len(cells) > ci + 2 else ""
            ntype = cells[ci + 3] if len(cells) > ci + 3 else ""
            ref = cells[ci + 4] if len(cells) > ci + 4 else ""
            segs = [clean(html.unescape(x)) for x in re.split(r"<[^>]+>", re.sub(r"<script.*?</script>", "", block, flags=re.S))]
            segs = [x for x in segs if x]
            country = segs[segs.index(ref) + 1] if ref in segs and segs.index(ref) + 1 < len(segs) else ""
            title = clean(title.replace("Open in a new window", ""))
            if pub and pub < cut:
                stop = True; continue
            if (dl and dl < t) or SKIP.search(ntype):
                continue
            sector, method = classify(title)
            new.append({
                "id": f"UNGM-{nid}", "source": f"UNGM ({agency})" if agency else "UNGM", "group": "", "sector": sector,
                "nature": "", "cpv": "", "classification": method, "country": iso3(country) or country[:40],
                "buyer": agency[:120], "title": title[:300], "notice_type": ntype, "stage": "tender",
                "access": "International (UN)", "published": str(pub or ""), "deadline": str(dl or ""),
                "value": "", "currency": "", "link": f"{BASE}/Public/Notice/{nid}", "contact": "", "lang": "",
                "ref": ref[:60],
            })
        if stop:
            break
        page += 1
        polite(0.7)
    rows, _ = rolling("ungm", new, max_age_days=400)
    log.info("UNGM total active %s, new %d, cache %d (pages %d)", total, len(new), len(rows), page)
    return rows, {"new": len(new), "total_active": total}
