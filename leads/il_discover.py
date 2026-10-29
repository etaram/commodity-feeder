"""Israel: find the tenders / calls-for-proposals page(s) of every body in data/israel/bodies.csv.

For each body with a website: open the home page (robots.txt respected), score its links (מכרזים, קולות קוראים,
הליכי רכש, tender, michrazim ...), follow up to two levels when the first hit is a hub page, and keep the pages that
actually list notices. Re-checks a body every 30 days, or sooner when its pages stopped yielding notices.
Run: python -m leads.il_discover [max_bodies] [minutes]
"""
import csv
import re
import datetime as dt
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from .common import log
from .il_registry import FIELDS, OUT
from .il_web import candidate_links, extract, fetch

COMMON_PATHS = ["/tenders", "/Tenders", "/michrazim", "/he/tenders", "/מכרזים", "/tenders/", "/he/מכרזים",
                "/procurement", "/he/procurement", "/Pages/tenders.aspx"]


MUNI = {"municipality", "local_council", "regional_council", "religious_council"}


def _guesses(body):
    en = re.sub(r"[^a-z\- ]", "", (body.get("name_en") or "").lower()).strip()
    if not en or body["type"] not in ("municipality", "local_council"):
        return []
    slugs = dict.fromkeys([en.replace(" ", "-"), en.replace(" ", "").replace("-", ""), en.split(" ")[0]])
    return [f"https://www.{s}.muni.il" for s in slugs if len(s) > 2]


def _named(body, txt):
    short = re.sub(r'["\'״׳\-]', "", body.get("name_short") or "")
    if body["type"] not in MUNI or not short:
        return True
    page = re.sub(r'["\'״׳\-]', "", txt[:60000])
    return short in page or short.replace(" ", "") in page.replace(" ", "")


def _home(body):
    """The body's verified home page: registry website first, then .muni.il guesses for authorities."""
    sites = [body["website"]] if body["website"] else []
    sites += [g for g in _guesses(body) if g not in sites]
    first, last = None, "no website"
    for site in sites:
        if not site.startswith("http"):
            site = "https://" + site
        for u in (site, ("http://" if site.startswith("https") else "https://") + urlparse(site).netloc):
            st, final, txt = fetch(u)
            last = st
            if st == "ok":
                if _named(body, txt):
                    return st, final, txt, site
                first = first or (st, final, txt, site)
                break
            if st in ("robots", "blocked"):
                first = first or (st, final, txt, site)
                break
    return first or (f"unreachable ({last})", "", "", body["website"])


def discover(body):
    st, final, txt, site = _home(body)
    if site and site != body["website"]:
        body["website"], body["website_source"] = site, "verified guess"
    if st != "ok":
        return {"status": f"home {st}", "tenders_urls": ""}
    pages = {}
    cands = candidate_links(final, txt)[:4]
    if not cands:
        root = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
        for path in COMMON_PATHS[:6]:
            s2, f2, t2 = fetch(urljoin(root, path))
            if s2 == "ok" and len(extract(f2, t2)) >= 2:
                cands = [f2]
                break
    for u in cands:
        if len(pages) >= 3:
            break
        s2, f2, t2 = fetch(u)
        if s2 != "ok":
            continue
        items = extract(f2, t2)
        if len(items) >= 1:
            pages[f2] = len(items)
        else:
            # hub page (e.g. "מכרזים" menu): one more level
            for u2 in candidate_links(f2, t2)[:3]:
                if u2 in pages or u2 == u:
                    continue
                s3, f3, t3 = fetch(u2)
                if s3 == "ok":
                    n = len(extract(f3, t3))
                    if n >= 1:
                        pages[f3] = n
                if len(pages) >= 3:
                    break
    if not pages:
        return {"status": "no tender page found" if cands else "no tender link on home page", "tenders_urls": ""}
    best = sorted(pages.items(), key=lambda x: -x[1])
    return {"status": f"ok ({sum(pages.values())} items seen)", "tenders_urls": " | ".join(u for u, _ in best)}


def run(max_bodies=600, minutes=50):
    rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
    today = dt.date.today()

    def due(r):
        if not r["website"] and not r.get("name_en"):
            return False
        if not r["last_discovered"]:
            return True
        age = (today - dt.date.fromisoformat(r["last_discovered"])).days
        if r["tenders_urls"] and r.get("open_items") == "0":
            return age >= 7
        return age >= 30

    todo = sorted([r for r in rows if due(r)], key=lambda r: (bool(r["last_discovered"]), int(r["priority"])))[:max_bodies]
    log.info("discovery: %d bodies due of %d", len(todo), len(rows))
    end = time.time() + minutes * 60
    found = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(discover, r): r for r in todo}
        for f in as_completed(futs):
            r = futs[f]
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                res = {"status": f"error {type(e).__name__}", "tenders_urls": ""}
            r.update(res)  # discover() may also correct r["website"]
            r["last_discovered"] = today.isoformat()
            found += bool(res["tenders_urls"])
            if time.time() > end:
                log.info("discovery: time budget reached")
                for x in futs:
                    x.cancel()
                break
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    log.info("discovery: %d of %d checked bodies have a tenders page; total with page %d", found, len(todo),
             sum(1 for r in rows if r["tenders_urls"]))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 600, int(sys.argv[2]) if len(sys.argv) > 2 else 50)
