"""Build data/benchmark_registry.csv: ONE designated benchmark per Master row.

Inputs
  data/master_rows.csv            Master row list
  data/prices.csv                 latest feed selection (designated feed source per row + check)
  tools/manual_sources.csv        prices already in the sheet from manual research (row, family, product)
Rule
  designated = the most reliable tier (T1 exchange > T2 official > T3 assessment > T4 trade statistics);
  on a tie the automated feed wins so the row keeps updating; a manual benchmark stays designated only when it
  is strictly more reliable than anything the feed offers (the scheduled search then refreshes it from that source).
Output columns
  row,id,hs6,name_full,designated_key,designated_source,tier,benchmark_product,mode(feed|manual),check_key
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from feeder.labels import product_from_feed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"

TIER_OF_KEY = {"yahoo": 1, "westmetall": 1, "em_global": 1, "derived": 1, "eu_agri": 2, "ssb": 2,
               "dtn": 3, "scrapmonster": 3, "smi": 3, "cn_spot": 3, "comext": 4, "census": 4, "comtrade": 4}
SOURCE_NAME = {
    "yahoo": "CME/NYMEX/COMEX/ICE futures (Yahoo Finance)",
    "westmetall": "LME official cash settlement (via Westmetall)",
    "em_global": "Exchange futures (ICE/Bursa/OSE via Eastmoney)",
    "derived": "Exchange benchmark of the same good (converted)",
    "eu_agri": "European Commission Agri-food Data Portal",
    "ssb": "Statistics Norway (SSB)",
    "dtn": "DTN Retail Fertilizer Trends",
    "scrapmonster": "Institute for Rare Earths and Metals (via ScrapMonster)",
    "smi": "Strategic Metals Invest",
    "cn_spot": "100ppi China spot (ex-VAT)",
    "comext": "Eurostat Comext (EU import unit value)",
    "census": "US Census (US import unit value)",
    "comtrade": "UN Comtrade (import unit value)",
    "manual_te": "Trading Economics (exchange/market quote, manual)",
    "manual_te_spot": "Trading Economics (spot quote, manual)",
    "manual_wb": "World Bank Pink Sheet (monthly, manual)",
    "manual_nbs": "China NBS 10-day market prices (manual)",
    "manual_usda": "USDA AMS Market News (manual)",
    "manual_gdt": "Global Dairy Trade auction (manual)",
    "manual_spices": "Spices Board India (manual)",
    "manual_dtn": "DTN Retail Fertilizer Trends (manual)",
    "manual_irem": "IREM / dealer assessment (manual)",
}
MANUAL_TIER = {"manual_te": 1, "manual_gdt": 1, "manual_wb": 2, "manual_nbs": 2, "manual_usda": 2,
               "manual_spices": 2, "manual_te_spot": 3, "manual_dtn": 3, "manual_irem": 3}
TIER_LABEL = {1: "T1 Exchange benchmark", 2: "T2 Official market reporting", 3: "T3 Industry assessment",
              4: "T4 Trade statistics (unit value)"}


def hs_full():
    out = {}
    with open("/root/harmonized-system/data/harmonized-system.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["hscode"]] = r["description"]
    return out


def main():
    master = {int(r["row"]): r for r in csv.DictReader(open(D / "master_rows.csv", encoding="utf-8"))}
    layer_a = {r: m["name"] for r, m in master.items() if m["layer"] == "API"}
    feed = {int(r["row"]): r for r in csv.DictReader(open(D / "prices.csv", encoding="utf-8"))}
    manual = {int(r["row"]): r for r in csv.DictReader(open(ROOT / "tools" / "manual_sources.csv", encoding="utf-8"))}
    full = hs_full()
    rows = []
    for row, m in sorted(master.items()):
        f = feed.get(row); mn = manual.get(row)
        ft = TIER_OF_KEY.get(f["source_key"], 9) if f else 9
        mt = MANUAL_TIER.get(mn["family"], 9) if mn else 9
        force = mn and mn.get("force") == "feed"
        if mn and not force and mt < ft:
            key, tier, prod, mode = mn["family"], mt, mn["product"], "manual"
            chk = f["source_key"] if f else ""
        elif f:
            key, tier, prod, mode = f["source_key"], ft, product_from_feed(f, layer_a), "feed"
            chk = f.get("check_source", "")
        else:
            key, tier, prod, mode, chk = "", "", "", "none", ""
        name = m["name"]
        if m["layer"] == "SEARCH" and m["hs6"] in full:
            name = full[m["hs6"]]
        rows.append({"row": row, "id": m["id"], "hs6": m["hs6"], "name_full": name, "designated_key": key,
                     "designated_source": SOURCE_NAME.get(key, key), "tier": TIER_LABEL.get(tier, ""),
                     "benchmark_product": prod, "mode": mode, "check": chk})
    with open(D / "benchmark_registry.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(Counter(r["mode"] for r in rows), Counter(r["tier"] for r in rows))
    print(Counter(r["designated_key"] for r in rows).most_common())


if __name__ == "__main__":
    sys.exit(main())
