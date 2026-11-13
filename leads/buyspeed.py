"""US state procurement portals on Periscope BuySpeed Online (the states' own official portals): the public Open Bids
list of each state (bso/view/search/external/advancedSearchBid.xhtml?openBids=true): bid number, organisation,
description, bid opening (closing) date, status, link to the bid's public detail page.

Access (checked 2026-11-13 from the server): anonymous HTML, no sign-in for the list; robots.txt of oregonbuys.gov
disallows only /craft. The list is a PrimeFaces data table: the first 25 rows come with the page and further pages are
read with the table's own paging request (same form, same view state), politely (1.5 s between pages).
Open on 13 Nov 2026: Massachusetts (COMMBUYS) 902, Oregon 176; Nevada and New Jersey listed too.
OPEN = a bid opening date today or later (in BuySpeed the 'Bid Opening Date' is the response deadline); the time zone
is the state's own and is not on the list."""
import datetime as dt
import html
import re
import time

from .common import CACHE, clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

PORTALS = [  # (key, base URL, state ISO-3166-2, buyer label)
    ("ma", "https://www.commbuys.com", "US-MA", "Commonwealth of Massachusetts"),
    ("or", "https://oregonbuys.gov", "US-OR", "State of Oregon"),
    ("nv", "https://nevadaepro.com", "US-NV", "State of Nevada"),
    ("nj", "https://www.njstart.gov", "US-NJ", "State of New Jersey"),
]
PATH = "/bso/view/search/external/advancedSearchBid.xhtml?openBids=true"
MAX_PAGES = 80
TR = re.compile(r'<tr data-ri="\d+"[^>]*>(.*?)</tr>', re.S)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TH = re.compile(r'<th[^>]*role="columnheader"[^>]*>(.*?)</th>', re.S)


def _txt(s):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))


def _date(s):
    s = _txt(s)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return str(dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))))
        except ValueError:
            return ""
    return ""


def parse(page, base, state, buyer_default, fetched):
    """Rows of one result page. Columns are found by their header text, so a column order change is not a silent error."""
    heads = [_txt(h).lower() for h in TH.findall(page)]
    def col(*words):
        return next((i for i, h in enumerate(heads) if all(w in h for w in words)), -1)
    i_no, i_org, i_desc = col("bid", "#") if col("bid", "#") >= 0 else col("bid", "number"), col("organization"), col("description")
    i_open, i_status = col("opening"), col("status")
    rows = []
    for tr in TR.findall(page):
        cells = TD.findall(tr)
        if len(cells) < 3:
            continue
        a = re.search(r'href="([^"]*bidDetail[^"]*)"', tr)
        no = _txt(cells[i_no]) if 0 <= i_no < len(cells) else _txt(cells[0])
        desc = _txt(cells[i_desc]) if 0 <= i_desc < len(cells) else ""
        if not no or not desc:
            continue
        status = _txt(cells[i_status]).lower() if 0 <= i_status < len(cells) else ""
        if re.search(r"cancel|award|closed", status):
            continue
        org = _txt(cells[i_org]) if 0 <= i_org < len(cells) else ""
        sector, how = classify(desc)
        link = base + html.unescape(a.group(1)).replace("&amp;", "&") if a else base + PATH
        rows.append({"id": f"BSO-{state[-2:]}-" + re.sub(r"[^A-Za-z0-9]+", "-", no)[:80], "source": f"{buyer_default} e-procurement (BuySpeed)",
                     "group": "", "sector": sector, "nature": "", "cpv": "", "classification": how, "country": "USA",
                     "buyer": (f"{org}, {buyer_default}" if org and buyer_default.split()[-1] not in org else org or buyer_default)[:120],
                     "title": desc[:300], "notice_type": "Open bid", "stage": "tender", "region_code": state,
                     "access": "State supplier registration usually needed to respond",
                     "published": "", "deadline": _date(cells[i_open]) if 0 <= i_open < len(cells) else "",
                     "deadline_basis": "bid_opening_date", "value": "", "currency": "", "link": link,
                     "source_url": base + PATH, "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def _next_payload(page, first):
    """The data table's own paging request: form id, table id and view state are read from the page."""
    vs = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', page)
    tbl = re.search(r'<div id="([^"]+)" class="ui-datatable[^"]*"', page)
    if not vs or not tbl:
        return None
    tid = tbl.group(1)
    form = tid.split(":")[0]
    return {"javax.faces.partial.ajax": "true", "javax.faces.source": tid, "javax.faces.partial.execute": tid,
            "javax.faces.partial.render": tid, tid: tid, f"{tid}_pagination": "true", f"{tid}_first": str(first),
            f"{tid}_rows": "25", f"{tid}_encodeFeature": "true", form: form, "javax.faces.ViewState": vs.group(1)}


def fetch_portal(s, key, base, state, buyer, fetched):
    r = s.get(base + PATH, timeout=60)
    r.raise_for_status()
    page = r.text
    tot = re.search(r"\d+-\d+ of (\d+)", page)
    total = int(tot.group(1)) if tot else 0
    rows = parse(page, base, state, buyer, fetched)
    heads = TH.findall(page)
    first = 25
    while first < total and first // 25 < MAX_PAGES:
        p = _next_payload(page, first)
        if not p:
            break
        time.sleep(1.5)
        rr = s.post(base + "/bso/view/search/external/advancedSearchBid.xhtml", data=p, timeout=60,
                    headers={"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest"})
        if rr.status_code != 200:
            break
        body = html.unescape(rr.text) if "<![CDATA[" in rr.text else rr.text
        got = parse("".join(f'<th role="columnheader">{h}</th>' for h in heads) + body, base, state, buyer, fetched)
        if not got:
            break
        rows += got
        first += 25
    return rows, total


def fetch():
    s = session()
    t = str(today())
    out, meta, ok = [], {}, 0
    for key, base, state, buyer in PORTALS:
        try:
            rows, total = fetch_portal(s, key, base, state, buyer, t)
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.warning("BuySpeed %s: %s", key, str(e)[:120]); meta[f"{key}_failed"] = 1; continue
        meta[f"{key}_listed"], meta[f"{key}_read"] = total, len(rows)
        out += rows
    if not ok:
        raise RuntimeError("BuySpeed: no state portal answered; previous snapshot kept")
    out, q = quarantine_future(out, "buyspeed")
    out = [x for x in out if x["deadline"] and x["deadline"] >= t]
    # a state that did not answer keeps its earlier rows as history (stale, not active), like Bonfire hubs
    import json
    failed = {st[-2:] for key, _, st, _ in PORTALS if meta.get(f"{key}_failed")}
    p = CACHE / "buyspeed.jsonl"
    if failed and p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["id"].split("-")[1] in failed and (r.get("deadline") or "") >= t:
                    r["stale"] = True; out.append(r)
    keep, _ = snapshot("buyspeed", list({x["id"]: x for x in out}.values()))
    log.info("BuySpeed states: %d open kept; %s", len(keep), ", ".join(f"{k} {v}" for k, v in meta.items()))
    meta.update(new=len(keep), quarantined=q, parts_failed=sum(1 for k in meta if k.endswith("_failed")))
    return keep, meta
