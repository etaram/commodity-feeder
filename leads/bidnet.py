"""BidNet Direct (US public-sector bids from state and local agencies and member agencies): the public list of open
solicitations (https://www.bidnetdirect.com/public/solicitations/open; 25,627 open on 13 Nov 2026), server-rendered,
25 per page, at most 400 pages per listing, so the collector walks one listing per state
(/<state>/solicitations/open-bids/pageN) and the national listing as a fallback.

Per row: title, location (state), published and closing dates, notice id and link; the agency is on the detail page
only, so buyer reads 'Public agency, <State> (via BidNet Direct)'. 'Federal Bids' rows are skipped (SAM.gov is read
directly). OPEN = a closing date today or later.
Access (checked 2026-11-13 from the server): public list, no sign-in; robots.txt respected; 1 s between pages.
Downloading documents and bidding need a BidNet / agency registration; reading the list does not."""
import datetime as dt
import html as H
import re
import time
from urllib.robotparser import RobotFileParser

from .common import clean, log, quarantine_future, rolling, session, today
from .sectors import classify

BASE = "https://www.bidnetdirect.com"
STATES = ["alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "district-of-columbia",
          "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
          "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new-hampshire",
          "new-jersey", "new-mexico", "new-york", "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
          "rhode-island", "south-carolina", "south-dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington",
          "west-virginia", "wisconsin", "wyoming", "puerto-rico", "guam"]
ROW = re.compile(r'<tr data-index="\d+" class="mets-table-row.*?</tr>', re.S)
BUDGET_S = 1500


def _t(x):
    return clean(H.unescape(re.sub(r"<[^>]+>", " ", x or "")))


def _d(s):
    try:
        return str(dt.datetime.strptime(s.strip(), "%m/%d/%Y").date())
    except ValueError:
        return ""


def parse(page, fetched):
    rows = []
    for r in ROW.findall(page):
        href = re.search(r'href="([^"]+/solicitations/open-bids/[^"]+)"', r)
        kind = re.search(r'data-mets-tooltip="([^"]+)"', r)
        kind = H.unescape(kind.group(1)) if kind else ""
        if not href or kind.lower().startswith("federal"):
            continue
        title = _t((re.search(r'class="rowTitle">(.*?)</span>', r, re.S) or [None, ""])[1])
        loc = _t((re.search(r'class="location">(.*?)</span>', r, re.S) or [None, ""])[1])
        pub = _d(_t((re.search(r'publicationDate">.*?dateValue">(.*?)</span>', r, re.S) or [None, ""])[1]))
        clo = _d(_t((re.search(r'closingDate[^"]*">.*?dateValue">(.*?)</span>', r, re.S) or [None, ""])[1]))
        nid = re.search(r'searchResultSol_notice_(\d+)|/(\d{6,})\?', r)
        nid = (nid.group(1) or nid.group(2)) if nid else ""
        if not title or not nid:
            continue
        sector, how = classify(title)
        link = H.unescape(href.group(1))
        rows.append({"id": f"BIDNET-{nid}", "source": "BidNet Direct (USA state and local)", "group": "", "sector": sector, "nature": "",
                     "cpv": "", "classification": how, "country": "USA", "buyer": f"Public agency, {loc} (via BidNet Direct)" if loc else "Public agency (via BidNet Direct)",
                     "title": title[:300], "notice_type": kind or "Open solicitation", "stage": "tender",
                     "access": "BidNet Direct or agency vendor registration needed for documents and bidding",
                     "published": pub, "deadline": clo, "value": "", "currency": "", "link": link.split("?")[0],
                     "source_url": BASE + "/public/solicitations/open", "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def fetch():
    t = str(today())
    s = session()
    rp = RobotFileParser()
    try:
        rp.parse(s.get(BASE + "/robots.txt", timeout=30).text.splitlines())
    except Exception:  # noqa: BLE001
        rp.parse([])
    out, pages, t0 = {}, 0, time.time()
    listings = [f"/{st}/solicitations/open-bids" for st in STATES] + ["/solicitations/open-bids"]
    for base in listings:
        prev = None
        for n in range(1, 401):
            if time.time() - t0 > BUDGET_S:
                break
            url = BASE + base + ("" if n == 1 else f"/page{n}")
            if not rp.can_fetch("*", url):
                log.info("BidNet: robots.txt disallows %s", base); break
            try:
                r = s.get(url, timeout=45)
            except Exception as e:  # noqa: BLE001
                log.warning("BidNet %s: %s", base, type(e).__name__); break
            pages += 1
            if r.status_code != 200:
                break
            got = parse(r.text, t)
            ids = tuple(x["id"] for x in got)
            if not got or ids == prev:
                break
            prev = ids
            for x in got:
                out[x["id"]] = x
            time.sleep(1.0)
    rows, q = quarantine_future(list(out.values()), "bidnet")
    rows = [x for x in rows if x["deadline"] and x["deadline"] >= t]
    keep, _ = rolling("bidnet", rows)
    log.info("BidNet: %d open (closing today or later), %d kept, %d quarantined; %d pages in %d s",
             len(rows), len(keep), q, pages, int(time.time() - t0))
    return keep, {"new": len(rows), "quarantined": q, "pages": pages}
