"""Leads engine: tenders (TED, World Bank, mr.gov.il) + US import buyers and suppliers (ImportYeti).

  python -m leads.run --source ted|worldbank|mrgov|importyeti   one source -> data/leads/partial/<source>.json
  python -m leads.run --merge                                    -> data/leads/*.csv for the Leads sheet
"""
import argparse
import csv
import datetime as dt
import json
import logging
import re
import sys
import traceback

from .common import DATA, LEADS, PARTIAL, benchmarks, fmt_bench, log, master_rows, save_partial, today
from .taxonomy import BY_ID, CH2GROUP

TENDER_SOURCES = ["ted", "worldbank", "mrgov"]
STOP = {"products", "other", "than", "with", "from", "parts", "thereof", "whether", "nonalloy", "including",
        "articles", "prepared", "preserved", "fresh", "chilled", "frozen", "similar", "suitable", "kind", "used"}


def run_source(name):
    if name == "ted":
        from . import ted as m
    elif name == "worldbank":
        from . import worldbank as m
    elif name == "mrgov":
        from . import mrgov as m
    elif name == "importyeti":
        from . import importyeti as m
    else:
        raise SystemExit(f"unknown source {name}")
    rows, meta = m.fetch()
    save_partial(name, rows, meta)
    log.info("%s: %d rows", name, len(rows))


def _rates():
    try:
        from feeder.fx import usd_per_unit
        return usd_per_unit()[0]
    except Exception:  # noqa: BLE001
        return {"EUR": 1.08, "ILS": 0.27, "GBP": 1.27}


def _group_bench(bm):
    out = {}
    for gid, g in BY_ID.items():
        out[gid] = " | ".join(fmt_bench(bm[r]) for r in g["ref"] if r in bm)
    return out


def score(r, usd, days, new):
    """0-100: size of the order, time left to bid, how precisely it matches a tracked commodity, region."""
    v = 8 if usd == "" else 4 if usd < 50_000 else 10 if usd < 250_000 else 18 if usd < 1_000_000 else \
        25 if usd < 5_000_000 else 30
    d = 10 if days == "" else 0 if days < 3 else 10 if days <= 7 else 20 if days <= 30 else 15
    m = r.get("match")
    m = 15 if m in (None, "") else 20 if m >= 5 else 14 if m >= 4 else 8
    reg = 20 if r["country"] == "ISR" else 15 if r["source"] == "World Bank" else 10
    return v + d + m + reg + (5 if new else 0) + (5 if r.get("contact") else 0)


def merge_tenders(bm, seen):
    rates, gb, t = _rates(), _group_bench(bm), today()
    rows, status = [], []
    for s in TENDER_SOURCES:
        p = PARTIAL / f"{s}.json"
        if not p.exists():
            status.append([s, "", 0, "no data"]); continue
        j = json.loads(p.read_text())
        status.append([s, j.get("ran", ""), len(j["rows"]), "OK" if j["rows"] else "EMPTY"])
        rows += j["rows"]
    out = []
    for r in rows:
        g = BY_ID.get(r["group"], {})
        first = seen.setdefault(r["id"], str(t))
        usd = ""
        if r.get("value") not in ("", None) and r.get("currency") in rates:
            usd = round(float(r["value"]) * rates[r["currency"]])
        dl = r.get("deadline") or ""
        days = (dt.date.fromisoformat(dl) - t).days if dl else ""
        new = (t - dt.date.fromisoformat(first)).days <= 2
        out.append({
            "score": score(r, usd, days, new),
            "new": "NEW" if new else "",
            "deadline": dl, "days_left": days, "group": g.get("name", r["group"]), "source": r["source"],
            "country": r["country"], "buyer": r["buyer"], "title": r["title"], "est_value_usd": usd,
            "est_value": r.get("value", ""), "currency": r.get("currency", ""), "published": r["published"],
            "notice_type": r["notice_type"], "classification": r["classification"], "contact": r.get("contact", ""),
            "benchmark": gb.get(r["group"], ""), "link": r["link"], "first_seen": first, "id": r["id"],
        })
    out.sort(key=lambda x: (-x["score"], x["deadline"] or "9999"))
    return out, status


def _relevant(title, products, g):
    extra = " ".join([g.get("name", "")] + g.get("wb", []))
    words = {w for w in re.findall(r"[a-z]{4,}", f"{title} {extra}".lower()) if w not in STOP}
    p = products.lower()
    return "match" if any(w[:5] in p for w in words) else "unclear"


def merge_importyeti(bm):
    hs_rows = {}
    for r in master_rows():
        h = (r["hs6"] or "")[:4]
        if len(h) == 4:
            hs_rows.setdefault(h, []).append(int(r["row"]))
    imp, sup, n = [], [], 0
    for f in sorted((LEADS / "importyeti").glob("*.json")):
        p = json.loads(f.read_text()); n += 1
        h = p["hs4"]; g = BY_ID.get(CH2GROUP.get(h[:2], ""), {})
        title = re.sub(r"^\d{4}-", "", p["title"]).replace("-", " ").title()
        bench = next((fmt_bench(bm[r]) for r in hs_rows.get(h, []) if r in bm), "")
        recs = sorted(p["records"], key=lambda x: (-x["shipments_12m"], -x["total_shipments"]))
        for role, lst, cap in (("importer", imp, 10), ("supplier", sup, 8)):
            k = 0
            for x in recs:
                if x["role"] != role or (role == "importer" and x["forwarder"]):
                    continue
                k += 1
                if k > cap:
                    break
                lst.append({
                    "hs4": h, "heading": title[:70], "group": g.get("name", ""), "company": x["company"],
                    "country": x["country"], "shipments_12m": x["shipments_12m"],
                    "total_shipments": x["total_shipments"], "weight_t": x["weight_t"], "teu": x["teu"],
                    "hs_codes": x["hs_codes"], "products": x["products"][:100],
                    "relevance": _relevant(title, x["products"], g), "flags": x["flags"],
                    "address": x["address"][:70], "benchmark": bench, "profile": x["profile"], "scanned": p["scanned"],
                })
    return imp, sup, n


def write(name, rows, cols=None):
    LEADS.mkdir(parents=True, exist_ok=True)
    cols = cols or (list(rows[0].keys()) if rows else ["empty"])
    with open(LEADS / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def merge():
    bm = benchmarks()
    seen_p = LEADS / "seen.json"
    seen = json.loads(seen_p.read_text()) if seen_p.exists() else {}
    tenders, status = merge_tenders(bm, seen)
    cutoff = str(today() - dt.timedelta(days=120))
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    seen_p.write_text(json.dumps(seen, sort_keys=True, indent=0))
    imp, sup, n = merge_importyeti(bm)
    write("tenders.csv", tenders)
    write("importers.csv", imp)
    write("suppliers.csv", sup)
    iyp = PARTIAL / "importyeti.json"
    iym = json.loads(iyp.read_text()) if iyp.exists() else {}
    status.append(["importyeti", iym.get("ran", ""), n,
                   f"{n} HS headings cached; this run {iym.get('meta', {}).get('scanned', 0)}, "
                   f"due {iym.get('meta', {}).get('due', '')}"])
    gb = _group_bench(bm)
    write("groups.csv", [{"group": g["name"], "hs_chapters": " ".join(g["hs"]), "ted_cpv": " ".join(g["cpv"]),
                          "worldbank_keywords": ", ".join(g["wb"]), "mr_gov_categories": " ".join(g["mr"]),
                          "benchmark": gb.get(g["id"], "")} for g in BY_ID.values()])
    write("status.csv", [dict(zip(["source", "last_run_utc", "rows", "note"], s)) for s in status])
    log.info("tenders %d, importers %d, suppliers %d", len(tenders), len(imp), len(sup))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--source"); ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    try:
        if a.source:
            run_source(a.source)
        if a.merge:
            merge()
    except Exception:  # noqa: BLE001
        LEADS.mkdir(parents=True, exist_ok=True)
        (LEADS / f"error_{a.source or 'merge'}.txt").write_text(traceback.format_exc())
        raise


if __name__ == "__main__":
    sys.exit(main())
