"""Australia, Victoria: open tenders on Buying for Victoria's tender portal (tenders.vic.gov.au), the state's
official list of current tenders across departments, agencies and many councils.

Access (checked 2026-11-14): robots.txt allows the search list (/tender/search) and disallows /tender/view, /secure/
and /person/; we read only the public 'open' list, page by page, one call a second, and never open a notice page.
Each row links to its own notice (/tender/view?id=...) for the reader; that link is not fetched by us.
OPEN = a row in the open list whose closing date is today or later."""
import datetime as dt
import re
import time

import requests

from .common import clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

BASE = "https://www.tenders.vic.gov.au"
LIST = BASE + "/tender/search"
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"])}


def vic_date(s):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})\s*([ap]m))?", s or "", re.I)
    if not m or m.group(2).lower() not in MONTHS:
        return "", ""
    try:
        d = dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return "", ""
    hm = f"{m.group(4)}:{m.group(5)} {m.group(6).lower()} AEST/AEDT" if m.group(4) else ""
    return str(d), hm


def parse(html, ts, diag=None):
    rows = []
    starts = [(m.start(), m.group(1)) for m in re.finditer(r'id=["\']tenderRow(\d+)["\']', html)]
    for k, (pos, tid) in enumerate(starts):
        body = html[pos: starts[k + 1][0] if k + 1 < len(starts) else pos + 20000]
        code = clean((re.search(r'data-tender-code=["\']([^"\']*)', body) or [None, ""])[1])
        a = re.search(r'<a[^>]*href=["\'][^"\']*tender/view\?id=' + tid + r'[^"\']*["\'][^>]*>(.*?)</a>', body, re.S)
        title = clean(a.group(1)) if a else ""
        text = clean(body)
        buyer = clean((re.search(r"Issued by:\s*(.*?)</span>", body, re.S) or [None, ""])[1])
        state = clean((re.search(r'tender-row-state["\'][^>]*>(.*?)</span>', body, re.S) or [None, ""])[1])
        typ = clean((re.search(r'tender-row-state["\'][^>]*>.*?</span>\s*(?:<br\s*/?>\s*)?([^<]+)', body, re.S) or [None, ""])[1])
        unspsc = clean((re.search(r"UNSPSC:\s*(.*?)</span>", body, re.S) or [None, ""])[1])
        op = re.search(r"Opened\s+(.{0,60})", text)
        cl = re.search(r"Closing\s+(.{0,60})", text)
        opened = vic_date(op.group(1))[0] if op else ""
        dl, hm = vic_date(cl.group(1)) if cl else ("", "")
        if diag is not None and not diag:
            diag.update({"title": title[:60], "state": state, "closing": cl.group(1)[:40] if cl else "", "text": text[:300]})
        if not title or not dl or dl < ts or (state and state.lower() != "open"):
            continue
        sector, how = classify(title + " " + unspsc)
        rows.append({"id": f"AU-VIC-{tid}", "source": "Buying for Victoria tenders (Australia, VIC)", "group": "",
                     "sector": sector, "nature": "", "cpv": "", "unspsc": unspsc[:120], "classification": how,
                     "country": "AUS", "buyer": (buyer or "Victorian Government")[:120] + ", Victoria",
                     "title": title[:300], "notice_type": " | ".join(x for x in [typ, code] if x)[:120], "stage": "tender",
                     "access": "Victorian Government procurement (open to all suppliers; English)",
                     "published": opened, "deadline": dl, "deadline_basis": "closing date", "deadline_time": hm,
                     "value": "", "currency": "", "link": f"{BASE}/tender/view?id={tid}", "source_url": LIST + "?preset=open",
                     "fetched": ts, "contact": "", "lang": "en"})
    return rows


def fetch():
    s, ts = session(), str(today())
    out, calls, seen_pages = {}, 0, set()
    for page in range(1, 120):
        r = requests.Session.get(s, LIST, params={"preset": "open", "page": page}, timeout=60)
        calls += 1
        if r.status_code != 200:
            raise RuntimeError(f"Victoria tenders: page {page} HTTP {r.status_code}; previous snapshot kept")
        ids = tuple(re.findall(r'id=["\']tenderRow(\d+)', r.text))
        if page == 1:
            log.info("Victoria tenders page 1: %d bytes, %d rows, title %r", len(r.content), len(ids),
                     (re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S) or [None, ""])[1].strip()[:80])
        if not ids or ids in seen_pages:
            break
        seen_pages.add(ids)
        diag = {}
        got = parse(r.text, ts, diag)
        if page == 1 and not got:
            log.warning("Victoria tenders: page 1 rows not parsed; first row %s", diag)
        for x in got:
            out[x["id"]] = x
        if f"page={page + 1}" not in r.text:
            break
        time.sleep(1.0)
    if not out:
        raise RuntimeError("Victoria tenders: no open tender read; previous snapshot kept")
    rows, q = quarantine_future(list(out.values()), "victoria")
    keep, _ = snapshot("victoria", rows)
    log.info("Victoria tenders: %d open tenders (%d pages)", len(keep), calls)
    return keep, {"new": len(keep), "calls": calls, "quarantined": q, "complete_snapshot": 1, "deep_link": 1,
                  "note": "deep links point to /tender/view, which robots.txt asks crawlers not to fetch; we do not fetch it"}
