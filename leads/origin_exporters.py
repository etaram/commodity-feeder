"""Exporters and producers of commodities in their origin countries, from public trade directories (phase 1: Tridge).

The supplier universe is built from public-tender winners, so origin exporters of farm commodities (an Ethiopian coffee
exporter, an Ivorian cashew processor) were missing. This layer reads the server-rendered directory pages of Tridge
(dir.tridge.com/suppliers/...; robots.txt allows them, only /graphql is disallowed), walks the links between
category, category-country and product-country pages, and keeps the sellers each page lists: name, country, business
type and the products the page states.

A directory listing is the company's own claim. Every row carries its source page and the evidence level "directory",
and the Deal Desk shows it as "plausible: check" at most, never as a supported match. Nothing is sent to anyone.
Output: data/private/origin_exporters.csv (git-ignored), merged into the encrypted supplier index by webindex.py.
The crawl is gentle (one page every few seconds), resumes where it stopped, and refreshes each page about weekly."""
import csv
import json
import re
import time
from collections import deque
from pathlib import Path
from datetime import date, datetime, timezone

import requests

from .common import PRIVATE, log

BASE = "https://dir.tridge.com"
OUT = PRIVATE / "origin_exporters.csv"
STATE = PRIVATE / "origin_exporters_state.json"
UA = {"User-Agent": "SinderDealDesk/1.0 (supplier research; contact via sinder.pro)"}
DELAY = 4.0
SEEDS = ["/suppliers/category/agriculture-food", "/suppliers/category-country/coffee-ethiopia"]
LINK = re.compile(r'"(/suppliers/(?:category|category-country|product-country|product)/[a-z0-9-]+)"')
TYPES = {"food_manufacturing": "manufacturer", "farming_production_processing_packing": "producer", "trade": "trader",
         "distribution_wholesale": "distributor", "import_export": "trader", "retail": "retailer"}
COLS = ["supplier", "country", "type", "products", "main_sector", "source", "source_url", "evidence", "seen"]
ISO2 = None


def iso3(code2):
    global ISO2
    if ISO2 is None:
        try:
            import pycountry
            ISO2 = {c.alpha_2: c.alpha_3 for c in pycountry.countries}
        except Exception:  # noqa: BLE001
            ISO2 = {}
    return ISO2.get(code2, code2)


def apollo(html):
    i = html.find("window.__APOLLO_STATE__=")
    if i < 0:
        return {}
    try:
        j, _ = json.JSONDecoder().raw_decode(html[i + len("window.__APOLLO_STATE__="):])
        return j
    except ValueError:
        return {}


def parse_page(html, path):
    """Sellers on one directory page, and the directory links it shows."""
    st = apollo(html)
    prods = {k: v.get("localizedName") for k, v in st.items() if k.startswith("Product:")}
    cats = {k: (v.get("localizedName") or v.get("name")) for k, v in st.items() if k.startswith("Category:")}
    page_product = ""
    for k, v in st.items():  # the page's own product or category names the product for sellers listed without one
        if k.startswith("ShowroomMarketplaceSellerEntity") and v.get("code") and path.endswith("/" + v["code"]):
            ref = (v.get("product") or v.get("category") or {}).get("__ref", "")
            page_product = prods.get(ref) or cats.get(ref) or ""
    if not page_product:
        page_product = path.rsplit("/", 1)[-1].replace("-", " ")
    out = []
    for k, v in st.items():
        if not k.startswith("Seller:") or not v.get("name"):
            continue
        cc = re.search(r'"code\\?":\\?"([A-Z]{2})', json.dumps(v.get("country") or {}))
        products = [prods.get(p.get("__ref")) for p in v.get("supplyingProducts") or []]
        products = [p for p in products if p] or ([page_product] if "/category/" not in path else [])
        kinds = [TYPES.get(t, t.replace("_", " ")) for t in v.get("businessTypes") or []]
        out.append({"supplier": v["name"].strip()[:90], "country": iso3(cc.group(1)) if cc else "",
                    "type": ", ".join(dict.fromkeys(kinds)), "products": "; ".join(dict.fromkeys(products))[:160],
                    "main_sector": "Agriculture & food", "source": "Tridge directory",
                    "source_url": f"{BASE}/find-suppliers/basic/{v.get('code')}" if v.get("code") else BASE + path,
                    "evidence": "directory"})
    return out, sorted(set(LINK.findall(html)))


def load_rows():
    if not OUT.exists():
        return {}
    return {(r["supplier"].lower(), r["country"]): r for r in csv.DictReader(open(OUT, encoding="utf-8"))}


def main(max_pages=450, max_minutes=45):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    seen = st.get("seen", {})  # path -> date fetched
    queue = deque(st.get("queue") or SEEDS)
    # commodity pages first: the directory has thousands of pages, and the ones people search (coffee, rice, sesame,
    # cashew ... and their varieties, from the shared commodity table) must not wait weeks behind the rest
    try:
        tax = json.loads((Path(__file__).resolve().parent.parent / "dealdesk/lib/commodities.json").read_text(encoding="utf-8"))["commodities"]
        keys = {w for e in tax for t in e["terms"] + [a for v in e["varieties"].values() for a in v["a"]] for w in [t.lower().replace(" ", "-")] if len(w) >= 4}
        hot = [p for p in queue if any(k in p for k in keys)]
        queue = deque(hot + [p for p in queue if p not in set(hot)])
        log.info("origin exporters: %d commodity pages moved to the front of %d queued", len(hot), len(queue))
    except Exception as e:  # noqa: BLE001
        log.warning("origin exporters: commodity priority skipped: %s", e)
    rows = load_rows()
    today, t0, n, fails, streak = date.today().isoformat(), time.time(), 0, 0, 0
    # repair (10 Nov 2026): that day's run was refused on all 800 pages but marked them as read; they are queued again, first
    if not st.get("repaired_1110"):
        lost = [p for p, d in seen.items() if d == "2026-11-10"]
        for p in lost:
            del seen[p]
        queue = deque(lost + [p for p in queue if p not in set(lost)])
        log.info("origin exporters: %d pages refused on 10 Nov queued again", len(lost))
    s = requests.Session()
    s.headers.update(UA)
    while queue and n < max_pages and time.time() - t0 < max_minutes * 60:
        path = queue.popleft()
        last = seen.get(path)
        if last and (date.fromisoformat(today) - date.fromisoformat(last)).days < 7:
            continue
        try:
            r = s.get(BASE + path, timeout=30)
            n += 1
            if r.status_code != 200:
                # a refused page is not "seen": it goes to the back of the queue; after 10 refusals in a row the run
                # stops (the site is limiting us: slow down, do not push)
                fails += 1; streak += 1
                if fails == 1 or streak == 10:
                    log.warning("origin exporters: HTTP %s on %s", r.status_code, path)
                queue.append(path)
                if streak >= 10:
                    log.warning("origin exporters: 10 refusals in a row, stopping this run"); break
                time.sleep(DELAY * 2)
                continue
            streak = 0
            seen[path] = today
            got, links = parse_page(r.text, path)
            for x in got:
                key = (x["supplier"].lower(), x["country"])
                old = rows.get(key)
                if old:  # products from several pages add up
                    ps = list(dict.fromkeys([p for p in (old["products"] + "; " + x["products"]).split("; ") if p]))
                    old["products"] = "; ".join(ps)[:160]
                    old["seen"] = today
                else:
                    rows[key] = {**x, "seen": today}
            for ln in links:
                if ln not in seen or (date.fromisoformat(today) - date.fromisoformat(seen[ln])).days >= 7:
                    if ln not in queue:
                        queue.append(ln)
        except requests.RequestException as e:
            fails += 1
            log.warning("origin exporters %s: %s", path, str(e)[:120])
        time.sleep(DELAY)
    if not queue:  # a full pass done: start over from the seeds next week
        queue = deque(SEEDS)
    STATE.write_text(json.dumps({"seen": seen, "queue": list(queue)[:20000], "repaired_1110": True, "at": datetime.now(timezone.utc).isoformat()}))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: (r["country"], r["supplier"].lower())):
            w.writerow({c: r.get(c, "") for c in COLS})
    by = {}
    for r in rows.values():
        by[r["country"]] = by.get(r["country"], 0) + 1
    log.info("origin exporters: %s", json.dumps({"pages": n, "failed": fails, "queued": len(queue), "suppliers": len(rows),
                                                  "countries": len(by), "top": sorted(by.items(), key=lambda x: -x[1])[:12]}))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    main()
