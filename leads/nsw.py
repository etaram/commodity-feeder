"""Australia, New South Wales: open opportunities on buy.nsw (buy.nsw.gov.au/opportunity/search), the NSW Government
list of current tenders, RFQs, RFPs and EOIs from state agencies and councils.

Access (checked 2026-11-14): robots.txt disallows only /search; the opportunity list is public, server-rendered,
10 per page (?page=N, 1-based). We read it page by page, one call a second, no relay. Each row links to its own notice
(/prcOpportunity/<id>). OPEN = a listed opportunity whose 'Closes' date is today or later."""
import datetime as dt
import re
import time

import requests

from .common import clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

BASE = "https://buy.nsw.gov.au"
LIST = BASE + "/opportunity/search"
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def nsw_date(s):
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})(?:\s+(\d{1,2}:\d{2}))?", s or "")
    if not m or m.group(2).lower() not in MON:
        return "", ""
    try:
        return str(dt.date(int(m.group(3)), MON[m.group(2).lower()], int(m.group(1)))), (m.group(4) or "")
    except ValueError:
        return "", ""


def parse(html, ts):
    rows = []
    for li in re.split(r"<li>\s*(?=<h3>)", html)[1:]:
        li = li[:6000]
        oid = (re.search(r'href="/prcOpportunity/([0-9A-Fa-f-]{20,})"', li) or [None, ""])[1]
        title = clean((re.search(r"<h3>(.*?)</h3>", li, re.S) or [None, ""])[1])
        dl, hm = nsw_date(clean((re.search(r"Closes:</b>\s*([^<]+)", li) or [None, ""])[1]))
        cats = "; ".join(clean(x) for x in re.findall(r'<p class="subcat">(.*?)</p>', li, re.S))
        ref = clean((re.search(r'<ul class="pills">\s*<li>(.*?)</li>', li, re.S) or [None, ""])[1])
        desc = clean((re.search(r'<p class="limit[^"]*">(.*?)</p>', li, re.S) or [None, ""])[1])
        typ = clean((re.search(r"<dt>Opportunity type</dt>\s*<dd>(.*?)</dd>", li, re.S) or [None, ""])[1])
        buyer = clean((re.search(r"<dt>Agency</dt>\s*<dd>(.*?)</dd>", li, re.S) or [None, ""])[1])
        if not oid or not title or not dl or dl < ts:
            continue
        sector, how = classify(title + " " + cats + " " + desc[:200])
        rows.append({"id": f"AU-NSW-{oid}", "source": "buy.nsw opportunities (Australia, NSW)", "group": "", "sector": sector,
                     "nature": "", "cpv": "", "classification": how, "country": "AUS",
                     "buyer": ((buyer or "NSW Government") + ", New South Wales")[:120], "title": title[:300],
                     "description": desc[:500], "notice_type": " | ".join(x for x in [typ, ref, cats[:60]] if x)[:160],
                     "stage": "tender", "access": "NSW Government procurement (open to all suppliers; English)",
                     "published": "", "deadline": dl, "deadline_basis": "closes", "deadline_time": (hm + " Sydney time") if hm else "",
                     "value": "", "currency": "", "link": f"{BASE}/prcOpportunity/{oid}", "source_url": LIST,
                     "fetched": ts, "contact": "", "lang": "en"})
    return rows


def fetch():
    s, ts = session(), str(today())
    out, calls, total, prev = {}, 0, "?", None
    for page in range(1, 200):   # 1-based (?page=0 repeats page 1)
        r = requests.Session.get(s, LIST, params={"page": page}, timeout=60)
        calls += 1
        if r.status_code != 200:
            raise RuntimeError(f"NSW: page {page} HTTP {r.status_code}; previous snapshot kept")
        if page == 1:
            total = (re.search(r"of\s+(\d+)\s+results", r.text) or [None, "?"])[1]
        ids = tuple(re.findall(r'href="/prcOpportunity/([0-9A-Fa-f-]{20,})"', r.text))
        if not ids or ids == prev:
            break
        prev = ids
        for x in parse(r.text, ts):
            out[x["id"]] = x
        if f"?page={page + 1}" not in r.text and len(out) >= int(total if str(total).isdigit() else 0):
            break
        time.sleep(1.0)
    if not out:
        raise RuntimeError("NSW: no open opportunity read; previous snapshot kept")
    rows, q = quarantine_future(list(out.values()), "nsw")
    keep, _ = snapshot("nsw", rows)
    log.info("NSW: %d open opportunities (%s listed, %d pages)", len(keep), total, calls)
    return keep, {"new": len(keep), "listed": total, "calls": calls, "quarantined": q, "complete_snapshot": 1, "deep_link": 1}
