"""Israel monitor: daily scan of the tenders / calls pages of ~1,000 Israeli public bodies (data/israel/bodies.csv).

Each notice becomes a tender row (country ISR, region Israel) for the leads merge, and data/israel/items.csv keeps the
full current list for the sheet. New = first seen in the last 2 days. A notice stays open until its deadline, or for
45 days after it was first seen when no deadline could be read.
Run: python -m leads.run --source israel   (or python -m leads.israel)
"""
import csv
import datetime as dt
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .common import DATA, log
from .il_registry import FIELDS, OUT
from .il_web import extract, fetch as get
from .mrgov import HE_GROUP, _sector

ITEMS = DATA / "israel" / "items.csv"
SEEN = DATA / "israel" / "seen.json"
TYPE_EN = {"municipality": "municipality", "local_council": "local council", "regional_council": "regional council",
           "gov_company": "government company", "statutory": "statutory body", "cluster": "cluster of authorities",
           "water_corp": "water corporation", "municipal_company": "municipal company", "hospital": "hospital",
           "hmo": "health fund", "academic": "academic institution", "religious_council": "religious council",
           "drainage": "drainage authority", "infra": "infrastructure body", "company": "company"}
ITEM_FIELDS = ["first_seen", "new", "body", "body_type", "district", "kind", "number", "title", "deadline", "days_left",
               "published", "sector", "link", "page", "id"]


def _scan(body):
    out, pages_ok = [], 0
    for u in [x.strip() for x in body["tenders_urls"].split("|") if x.strip()][:3]:
        st, final, txt = get(u)
        if st != "ok":
            continue
        pages_ok += 1
        for it in extract(final, txt):
            it["page"] = final
            out.append(it)
    return pages_ok, out


def fetch_all(minutes=55, workers=20):
    rows = list(csv.DictReader(open(OUT, encoding="utf-8")))
    seen = json.loads(SEEN.read_text()) if SEEN.exists() else {}
    today = dt.date.today()
    todo = [r for r in rows if r["tenders_urls"]]
    log.info("israel: scanning %d bodies with tender pages (of %d in registry)", len(todo), len(rows))
    items, end = [], time.time() + minutes * 60
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_scan, r): r for r in todo}
        for f in as_completed(futs):
            r = futs[f]
            try:
                ok, got = f.result()
            except Exception:  # noqa: BLE001
                ok, got = 0, []
            r["last_scanned"] = today.isoformat()
            n_open = 0
            for it in got:
                norm_t = re.sub(r"\W+", "", it["title"])[:120]
                key = hashlib.sha1(f"{r['id']}|{norm_t}".encode()).hexdigest()[:16]
                first = seen.setdefault(key, today.isoformat())
                dl = it["deadline"]
                if dl and dl < today.isoformat():
                    continue
                if not dl and (today - dt.date.fromisoformat(first)).days > 45:
                    continue
                if not dl and it.get("published") and (today - dt.date.fromisoformat(it["published"])).days > 120:
                    continue
                n_open += 1
                items.append({**it, "id": f"IL-{key}", "first_seen": first, "body": r["name"], "body_id": r["id"],
                              "body_type": r["type"], "district": r.get("district", ""), "priority": r["priority"]})
            r["open_items"] = str(n_open) if ok else r.get("open_items", "")
            if time.time() > end:
                log.info("israel: time budget reached")
                for x in futs:
                    x.cancel()
                break
    # keep registry fresh
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    cutoff = (today - dt.timedelta(days=400)).isoformat()
    SEEN.write_text(json.dumps({k: v for k, v in seen.items() if v >= cutoff}, sort_keys=True, indent=0))
    # items file for the sheet
    dedup = {}
    for it in items:
        dedup.setdefault(it["id"], it)
    items = sorted(dedup.values(), key=lambda x: (x["first_seen"], x["deadline"] or "9999"), reverse=True)
    with open(ITEMS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ITEM_FIELDS, extrasaction="ignore")
        w.writeheader()
        for it in items:
            dl = it["deadline"]
            w.writerow({**it, "new": "NEW" if (today - dt.date.fromisoformat(it["first_seen"])).days <= 2 else "",
                        "body_type": TYPE_EN.get(it["body_type"], it["body_type"]),
                        "days_left": (dt.date.fromisoformat(dl) - today).days if dl else "",
                        "sector": _sector(it["title"])})
    log.info("israel: %d open notices from %d bodies (%d new today)", len(items),
             len({i["body_id"] for i in items}), sum(1 for i in items if i["first_seen"] == today.isoformat()))
    return items


def fetch():  # leads.run interface
    items = fetch_all()
    rows = []
    for it in items:
        t = it["title"]
        rows.append({
            "id": it["id"], "source": f"Israel - {TYPE_EN.get(it['body_type'], it['body_type'])}",
            "group": next((k for k, rx in HE_GROUP if re.search(rx, t)), ""), "sector": _sector(t), "nature": "",
            "cpv": "", "stage": "tender", "access": "Israeli bidders (home market)", "lang": "he", "country": "ISR",
            "buyer": it["body"], "title": t[:300], "classification": "keyword (he)",
            "notice_type": ("קול קורא" if it["kind"] == "call" else "מכרז") + (f" {it['number']}" if it["number"] else ""),
            "published": it.get("published", ""), "deadline": it["deadline"], "value": "", "currency": "",
            "link": it["link"], "contact": "",
        })
    return rows, {"bodies_scanned": sum(1 for _ in open(OUT, encoding="utf-8")) - 1, "open_notices": len(rows)}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    fetch_all()
