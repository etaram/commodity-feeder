"""Benchmark policy: one reference source per commodity, chosen by a fixed reliability hierarchy.

Tiers
  T1  Exchange benchmark        - settlement / front-month price on the reference exchange (LME, ICE, CME, Bursa, OSE)
  T2  Official market reporting - government price reporting (European Commission, Statistics Norway, USDA)
  T3  Industry assessment       - recognised price assessments and surveys (IREM, DTN, dealer quotes, 100ppi ex-VAT)
  T4  Trade statistics          - official customs unit values (Eurostat Comext, US Census, UN Comtrade), monthly

Rules
  * Each Master row has ONE designated benchmark source, stored in data/benchmark_map.csv and kept stable
    between runs. It is upgraded only when a higher tier becomes available; it is never silently swapped.
  * If the designated source has no fresh price in a run, the best available source is used for that run
    and the row is marked FALLBACK, naming the designated source.
  * HS rows that describe exactly the exchange-traded good (e.g. HS 740311 copper cathodes) take the same
    exchange benchmark as the layer-A row, converted to the HS row's unit.
  * A second, independent source is shown as a check price with the deviation in %.
"""
from __future__ import annotations

import csv
import copy
import datetime as dt

from .common import DATA, Price

TIER = {
    "yahoo": 1, "westmetall": 1, "em_global": 1, "derived": 1,
    "eu_agri": 2, "ssb": 2, "usda_mars": 2, "usda": 2, "usda_gdt": 1, "eia": 2,
    "dtn": 3, "scrapmonster": 3, "smi": 3, "cn_spot": 3,
    "comext": 4, "census": 4, "comtrade": 4,
}
TIER_LABEL = {1: "T1 Exchange benchmark", 2: "T2 Official market reporting",
              3: "T3 Industry assessment", 4: "T4 Trade statistics (unit value)"}
# preference inside a tier (lower is better)
INTRA = {"westmetall": 0, "yahoo": 1, "em_global": 2, "derived": 1,
         "eu_agri": 0, "ssb": 0, "usda_mars": 1, "usda": 1, "usda_gdt": 3, "eia": 1,
         "scrapmonster": 0, "dtn": 0, "smi": 1, "cn_spot": 2,
         "comext": 0, "census": 1, "comtrade": 2}
# freshness limit (days) for a source to count as available this run
MAX_AGE = {"yahoo": 5, "westmetall": 6, "em_global": 5, "derived": 6, "eu_agri": 30, "ssb": 30, "usda_mars": 30, "usda": 40, "usda_gdt": 21,
           "eia": 30, "dtn": 30, "scrapmonster": 60, "smi": 10, "cn_spot": 7, "comext": 150, "census": 150,
           "comtrade": 180}

# layer-A rows: which exchange feed is the reference
DESIGNATED_A = {21: "westmetall", 22: "westmetall", 23: "westmetall", 24: "westmetall", 25: "westmetall",
                26: "westmetall", 10: "em_global", 11: "em_global", 44: "em_global", 57: "em_global"}

OZ_PER_KG = 32.1507466
# HS row <- (layer-A row, factor from layer-A unit to HS unit, HS unit, note)
EQUIV = {
    1857: (21, 1, "USD/t", "LME copper"), 1905: (22, 1, "USD/t", "LME aluminium"),
    1932: (23, 1, "USD/t", "LME zinc"), 1890: (24, 1, "USD/t", "LME nickel"),
    1924: (25, 1, "USD/t", "LME lead"), 1941: (26, 1, "USD/t", "LME tin"),
    1679: (17, OZ_PER_KG, "USD/kg", "USD/oz x 32.1507 oz/kg"), 1675: (18, OZ_PER_KG, "USD/kg", "USD/oz x 32.1507 oz/kg"),
    1683: (19, OZ_PER_KG, "USD/kg", "USD/oz x 32.1507 oz/kg"), 1685: (20, OZ_PER_KG, "USD/kg", "USD/oz x 32.1507 oz/kg"),
    882: (2, 1, "USD/bbl", "Brent"), 893: (5, 1, "USD/MMBtu", "Henry Hub"), 888: (7, 1, "USD/MMBtu", "JKM LNG"),
    536: (33, 36.7437, "USD/t", "USD/bu x 36.7437 bu/t (wheat)"), 544: (36, 39.3683, "USD/t", "USD/bu x 39.3683 bu/t (corn)"),
    587: (37, 36.7437, "USD/t", "USD/bu x 36.7437 bu/t (soybeans)"), 542: (41, 68.894, "USD/t", "USD/bu x 68.894 bu/t (oats)"),
    729: (38, 1.102311, "USD/t", "USD/short ton x 1.102311"), 647: (39, 2204.62, "USD/t", "USD/lb x 2,204.62 lb/t"),
    657: (44, 1, "USD/t", "Bursa CPO"), 494: (45, 2.20462, "USD/kg", "USD/lb x 2.20462 lb/kg"),
    706: (47, 1, "USD/t", "ICE cocoa"), 691: (48, 2204.62, "USD/t", "USD/lb x 2,204.62 lb/t"),
    1482: (50, 2204.62, "USD/t", "USD/lb x 2,204.62 lb/t"), 1217: (57, 1, "USD/kg", "OSE RSS3"),
    545: (40, 22.0462, "USD/t", "USD/cwt x 22.0462 cwt/t"), 864: (11, 1, "USD/t", "ICE Newcastle"),
    883: (8, 1, "USD/gal", "NYMEX RBOB"), 884: (10, 1, "USD/t", "ICE gasoil"), 889: (13, 1, "USD/gal", "Mont Belvieu propane"),
    839: (15, 1, "USD/lb", "U3O8"), 64: (53, 2.20462, "USD/kg", "USD/lb live weight x 2.20462"),
    1317: (52, 1 / 2.35974, "USD/m3", "USD/1000 board ft / 2.35974 m3"),
}


def _age(p: Price, today: dt.date) -> int:
    try:
        return (today - dt.date.fromisoformat(p.price_date)).days
    except ValueError:
        return 9999


def derive(by: dict[int, list[Price]]) -> None:
    """Add exchange-benchmark candidates to HS rows that are the same good as a layer-A contract."""
    for row, (src, f, unit, note) in EQUIV.items():
        base = by.get(src, [])
        if not base:
            continue
        pref = DESIGNATED_A.get(src)
        base = sorted([b for b in base if TIER.get(b.source_key) == 1],
                      key=lambda b: (b.source_key != pref, INTRA.get(b.source_key, 9), b.price_date), reverse=False)
        if not base:
            continue
        b = base[0]
        d = copy.copy(b)
        d.row = row; d.unit_usd = unit; d.price_usd = b.price_usd * f
        d.calc = f"{b.calc} ; {note}" + (f" = {d.price_usd:,.4f} {unit}" if f != 1 else "")
        d.source = f"{b.source} [benchmark for this HS code]"
        d.source_key = "derived"; d.quality = "OK"
        by.setdefault(row, []).append(d)


def load_map() -> dict[int, dict]:
    p = DATA / "benchmark_map.csv"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return {int(r["row"]): r for r in csv.DictReader(f)}


def save_map(m: dict[int, dict]) -> None:
    with open(DATA / "benchmark_map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["row", "id", "name", "designated_source", "tier", "series", "since"])
        w.writeheader()
        for row in sorted(m):
            w.writerow(m[row])


def _key(c: Price, row: int):
    pref = DESIGNATED_A.get(row)
    return (TIER.get(c.source_key, 9), 0 if c.source_key == pref else 1, INTRA.get(c.source_key, 9),
            [-ord(ch) for ch in c.price_date])


def select(row: int, cands: list[Price], bmap: dict[int, dict], meta: dict, today: dt.date):
    """Return (benchmark, check, selection_note)."""
    fresh = [c for c in cands if _age(c, today) <= MAX_AGE.get(c.source_key, 30)]
    pool = fresh or cands
    best = min(pool, key=lambda c: _key(c, row))
    cur = bmap.get(row)
    note = "designated"
    if cur:
        des = [c for c in fresh if c.source_key == cur["designated_source"]]
        if des and TIER.get(best.source_key, 9) >= TIER.get(cur["designated_source"], 9):
            best = min(des, key=lambda c: _key(c, row))
        elif TIER.get(best.source_key, 9) < TIER.get(cur["designated_source"], 9):
            note = f"upgraded from {cur['designated_source']}"
            cur = None
        else:
            note = f"FALLBACK: designated {cur['designated_source']} has no fresh price"
    if cur is None and not note.startswith("FALLBACK"):
        bmap[row] = {"row": row, "id": meta["id"], "name": meta["name"], "designated_source": best.source_key,
                     "tier": TIER.get(best.source_key, 9), "series": best.source.split(" [")[0][:120],
                     "since": today.isoformat()}
        if note == "designated":
            note = "designated (new)"
    others = [c for c in cands if c is not best and c.source_key != best.source_key and c.unit_usd == best.unit_usd]
    check = min(others, key=lambda c: _key(c, row)) if others else None
    return best, check, note
