"""Checks for leads/commodity_norm.py, leads/commodity_stats.py and leads/landed_cost.py (upgrade brief section 11).
Run: PYTHONPATH=. python3 tests/test_commodities.py"""
import csv
import datetime as dt
import math
import random
from pathlib import Path

from leads.commodity_norm import SRC, normalise, to_tonne, price_type_of
from leads.commodity_stats import anomalies, changes, seasonality, monthly_means, stats_row, volatility, _clean
from leads.landed_cost import basis_gap, comparable, landed_cost

ROOT = Path(__file__).resolve().parent.parent


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def test_units():
    assert close(to_tonne(1.0, "USD/kg")[0], 1000.0), "kg to t"
    assert close(to_tonne(1.0, "USD/lb")[0], 1000.0 / 0.453592), "lb to t"
    assert close(to_tonne(1.0, "USD/short ton")[0], 1000.0 / 907.185), "short ton to t"
    assert close(to_tonne(1.0, "USD/long ton")[0], 1000.0 / 1016.05), "long ton to t"
    assert close(to_tonne(6.0, "USD/bu", "Wheat (HRW)")[0], 6.0 / 27.2155 * 1000.0), "wheat bushel"
    assert close(to_tonne(4.0, "USD/bu", "Corn - CBOT futures")[0], 4.0 / 25.4012 * 1000.0), "maize bushel"
    assert close(to_tonne(12.0, "USD/bu", "Soybeans")[0], 12.0 / 27.2155 * 1000.0), "soybean bushel"
    assert to_tonne(5.0, "USD/bu", "Mystery grain")[0] is None, "a bushel without a known product is not converted"
    assert to_tonne(94.59, "USD/bbl")[0] is None, "barrels are never converted to tonnes"
    assert to_tonne(2.9, "USD/MMBtu")[0] is None and to_tonne(2.7, "USD/gal")[0] is None, "energy and volume units stay as they are"
    assert to_tonne(100.0, "USD/t")[0] == 100.0, "USD/t as given"


def test_price_types_on_real_rows():
    rows = {r["id"]: r for r in csv.DictReader(open(SRC, encoding="utf-8"))}
    expect = {"L0001": ("futures", "false"), "L0020": ("spot", "true"), "H0092": ("spot", "true"), "H0351": ("spot", "true"),
              "H0160": ("index", "false"), "H0824": ("assessment", "true"), "H0657": ("spot", "true"), "H0914": ("assessment", "true"),
              "H0321": ("spot", "true"), "H0319": ("index", "false")}
    for rid, (kind, phys) in expect.items():
        assert rid in rows, f"{rid} missing from commodity_prices.csv"
        n = normalise(rows[rid])
        assert n["price_type_norm"] == kind, f"{rid}: {n['price_type_norm']} != {kind} ({rows[rid]['price_type']})"
        assert n["physical"] == phys, f"{rid}: physical {n['physical']} != {phys}"
    n = normalise(rows["L0001"])
    assert n["product"] == "Crude oil Brent" and n["grade"] == "Brent" and n["unit_canonical"] == "USD/bbl" and n["price_usd_t"] == "", "Brent row"
    n = normalise(rows["L0033"])
    assert n["grade"] == "HRW" and close(float(n["price_usd_t"]), float(rows["L0033"]["price_usd"]) / 27.2155 * 1000), "HRW wheat bushel to tonne"
    n = normalise(rows["H0366"])
    assert n["origin"] == "PER" and n["incoterm"] == "FOB", "stated origin and FOB basis on the USDA row"
    n = normalise(rows["H0824"])
    assert n["incoterm"] == "CIF" and n["delivery_location"] == "CIF China" and "6% min" in n["grade"], "IREM spec parsed"
    n = normalise(rows["H0319"])
    assert n["grade"] == "" and n["origin"] == "" and n["incoterm"] == "", "nothing guessed for a trade-statistics row"
    assert price_type_of("", "") == "unknown", "blank text is unknown"
    assert price_type_of("Executable offer, FOB", "T3") == "offer"


def test_futures_vs_physical():
    fut = {"product": "Wheat", "grade": "HRW", "price_type_norm": "futures", "price_usd": "6.3", "unit_canonical": "USD/bu"}
    phys = {"product": "Wheat", "grade": "HRW", "price_type_norm": "offer", "price_usd": "260", "unit_canonical": "USD/t", "incoterm": "FOB",
            "delivery_location": "FOB Gulf"}
    ok, why = comparable(fut, phys)
    assert not ok and any("futures" in w for w in why), f"futures vs physical must not be comparable: {why}"
    ok, why = comparable(dict(phys), dict(phys, price_usd="265"))
    assert ok and not why, f"same physical spec is comparable: {why}"
    ok, why = comparable(phys, dict(phys, grade="SRW"))
    assert not ok and any("grade" in w for w in why), "grades must match"
    idx = dict(phys, price_type_norm="index")
    ok, why = comparable(phys, idx)
    assert not ok and any("index" in w for w in why), "an index is not an executable price"
    ok, why = comparable(phys, dict(phys, unit_canonical="USD/bbl"))
    assert not ok and any("units" in w for w in why), "unconvertible units are not comparable"
    gaps = basis_gap(phys, dict(phys, incoterm="CIF", delivery_location="CIF Haifa"))
    assert gaps and "landed_cost" in gaps[-1], "a different basis points to landed_cost, never to a spread"


def test_landed_cost():
    r = landed_cost(260, "USD/t", "FOB", "USA", "ISR", handling=12, duty_pct=0, financing_days=45, rate_pct=8, loss_pct=0.5)
    assert "freight_usd_per_t" in r["missing"] and not r["complete"], "missing freight is reported, never guessed"
    assert r["freight_usd_per_t"] == 0.0 and r["goods_usd_per_t"] == 260.0
    full = landed_cost(260, "USD/t", "FOB", "USA", "ISR", freight_usd_per_t=40, handling=12, duty_pct=10, financing_days=45, rate_pct=8, loss_pct=0.5)
    assert full["complete"] and full["missing"] == []
    pre = 260 + 40 + 12 + (300 * 0.10)
    fin = pre * 0.08 * 45 / 365
    sub = pre + fin
    assert close(full["total_usd_per_t"], sub / (1 - 0.005)), f"total arithmetic {full}"
    cif = landed_cost(300, "USD/t", "CIF", "CHN", "ISR", freight_usd_per_t=40, handling=10, duty_pct=0, financing_days=0, rate_pct=0, loss_pct=0)
    assert cif["freight_usd_per_t"] == 0.0 and any("includes main carriage" in n for n in cif["notes"]), "CIF already carries freight"
    kg = landed_cost(1.2, "USD/kg", "EXW", "CHN", "ISR", freight_usd_per_t=60, handling=10, duty_pct=0, financing_days=0, rate_pct=0, loss_pct=0)
    assert close(kg["goods_usd_per_t"], 1200.0), "kg quote converted to tonnes"
    bbl = landed_cost(94.5, "USD/bbl", "FOB", "GBR", "ISR")
    assert bbl["total_usd_per_t"] is None and any("conversion" in m for m in bbl["missing"]), "barrels are not converted"
    blank = landed_cost(None, "", "", "", "")
    assert set(["price", "incoterm", "origin", "destination"]) <= set(blank["missing"])


def _synthetic(days=120, start_price=100.0, daily_sigma=0.01, seed=7):
    rnd = random.Random(seed)
    d0 = dt.date(2026, 7, 1)
    out, p = {}, start_price
    for i in range(days):
        d = d0 + dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        p *= math.exp(rnd.gauss(0, daily_sigma))
        out[d.isoformat()] = p
    return out


def test_volatility_and_anomaly():
    s = _synthetic()
    pts = _clean(s)
    v30, v90 = volatility(pts, 30), volatility(pts, 90)
    assert v30 is not None and v90 is not None, "a daily series of 120 days has both windows"
    assert 5 < v90 < 40, f"1% daily sigma annualises to about 16%: {v90}"
    assert volatility(pts[:15], 30) is None, "under 20 points gives no volatility"
    today = pts[-1][0]
    flags, _ = anomalies(pts, today)
    assert "sigma3" not in flags and "jump15" not in flags and "stale" not in flags, f"a calm series has no flags: {flags}"
    jump = dict(s)
    last = max(jump)
    jump[last] = s[last] * 1.4
    flags, notes = anomalies(_clean(jump), today)
    assert "jump15" in flags and "sigma3" in flags, f"a 40% last move is a jump and a 3-sigma outlier: {flags} {notes}"
    flags, _ = anomalies(pts, today + dt.timedelta(days=12))
    assert "stale" in flags, "a daily series 12 days old is stale"
    flags, _ = anomalies(pts, today + dt.timedelta(days=5))
    assert "stale" not in flags, "5 days is not stale for a daily series"
    ch = changes(pts)
    assert ch["1w"] is not None and ch["1m"] is not None and ch["3m"] is not None and ch["12m"] is None, f"changes within the window only: {ch}"
    row = stats_row("X1", "synthetic", s, today)
    assert row["freq"] == "daily" and row["vol_30d"] != "" and row["season_idx"] == "" and "24 needed" in row["season_note"]
    assert row["basis"].startswith("daily ") and "points" in row["basis"]
    single = stats_row("X2", "one point monthly", {"2026-08-31": 5.0}, dt.date(2026, 11, 5), hint="monthly")
    assert single["freq"] == "monthly" and single["anomaly"] == "", "a monthly point two months old is not stale"


def test_seasonality():
    short = {(2025, m): 100.0 + m for m in range(1, 13)}
    idx, note = seasonality(short)
    assert idx is None and "24 needed" in note, "under 24 months: blank with the reason"
    monthly = {}
    for y in (2022, 2023, 2024, 2025):
        for m in range(1, 13):
            monthly[(y, m)] = 100.0 * (1.2 if m in (6, 7) else 0.9 if m in (12, 1) else 1.0)
    idx, note = seasonality(monthly)
    assert idx is not None and len(idx) == 12 and abs(sum(idx) / 12 - 1.0) < 2e-3, "12 indices around 1.0 (rounded to 3 decimals)"
    assert idx[5] > 1.1 and idx[6] > 1.1 and idx[11] < 0.95 and idx[0] < 0.95, f"summer high, winter low: {idx}"
    daily = _synthetic(days=800)
    mm = monthly_means(_clean(daily))
    assert len(mm) >= 24 and seasonality(mm)[0] is not None, "daily data is averaged to months first"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all commodity checks passed")
