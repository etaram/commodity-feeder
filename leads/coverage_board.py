"""Coverage board: for each commodity of the taxonomy, how good the data is today. One row per commodity:
price rows at origin, how many are fresh (<= 14 days), the newest date, how many origins and sources carry a price,
and how many registry suppliers with a phone or e-mail we hold. Written to data/leads/coverage_board.csv so the
gaps (no fresh price, no reachable supplier) steer the next collection work instead of a blind sweep."""
import csv
import datetime as dt
import glob
import json
import re

from .common import LEADS, ROOT, log

FRESH = 14


def main():
    tax = json.load(open(ROOT / "dealdesk" / "lib" / "commodities.json", encoding="utf-8"))["commodities"]
    prices = list(csv.DictReader(open(LEADS / "origin_prices.csv", encoding="utf-8")))
    regs = []
    for f in glob.glob(str(LEADS / "registry_*.csv")) + [str(LEADS / x) for x in ("uganda_directory.csv", "eth_exporters.csv", "coffee_sellers.csv")]:
        try:
            regs += list(csv.DictReader(open(f, encoding="utf-8")))
        except OSError:
            pass
    today = dt.date.today()
    out = []
    for c in tax:
        pat = re.compile(r"\b(" + "|".join(re.escape(t) for t in c["terms"]) + r")", re.I)
        hs = tuple(c.get("hs") or [])
        mine = [p for p in prices if pat.search(f"{p.get('commodity', '')} {p.get('product', '')}") or (hs and (p.get("hs6") or "").startswith(hs))]
        ages = []
        for p in mine:
            try:
                ages.append((today - dt.date.fromisoformat(p["date"][:10])).days)
            except (ValueError, KeyError):
                pass
        fresh = sum(1 for a in ages if 0 <= a <= FRESH)
        sup = [r for r in regs if pat.search(f"{r.get('product', '')} {r.get('products', '')} {r.get('description', '')}")]
        reach = sum(1 for r in sup if (r.get("email") or r.get("phone") or r.get("contact") or "").strip())
        ok_price, ok_sup = fresh >= 1, reach >= 30
        out.append({"commodity": c["key"], "price_rows": len(mine), "fresh_rows": fresh, "newest_age_days": min([a for a in ages if a >= 0], default=""),
                    "price_origins": len({p.get("origin") for p in mine if p.get("origin")}), "price_sources": len({p.get("source") for p in mine}),
                    "registry_suppliers": len(sup), "reachable_suppliers": reach, "meets_target": "yes" if ok_price and ok_sup else "no",
                    "gap": "; ".join(x for x in ("" if ok_price else "no price newer than 14 days", "" if ok_sup else f"{reach} reachable registry suppliers (target 30)") if x)})
    out.sort(key=lambda r: (r["meets_target"] == "yes", r["fresh_rows"], r["reachable_suppliers"]))
    with open(LEADS / "coverage_board.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    met = sum(1 for r in out if r["meets_target"] == "yes")
    log.info("coverage board: %d of %d commodities meet the target; with a fresh price %d; without any price %d", met, len(out), sum(1 for r in out if r["fresh_rows"]), sum(1 for r in out if not r["price_rows"]))
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    for r in main():
        print(f"{r['commodity']:18} prices {r['price_rows']:4} fresh {r['fresh_rows']:3} age {str(r['newest_age_days']):>4} origins {r['price_origins']:3} | suppliers {r['registry_suppliers']:4} reach {r['reachable_suppliers']:4} | {r['meets_target']}")
