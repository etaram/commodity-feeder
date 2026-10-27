"""European Commission Agri-food Data Portal API (official weekly/monthly market prices). Free, no key.

For each product: unweighted average of euro-area Member State prices in the latest week reported.
Non-euro Member States are excluded so every price is genuinely in EUR.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics as st

from ..common import Price, session, log, polite_sleep

BASE = "https://api.tech.ec.europa.eu/agrifood/api"
NON_EURO = {"CZ", "DK", "HU", "PL", "RO", "SE"}
LINK = "https://agridata.ec.europa.eu/extensions/DataPortal/prices.html"

# (endpoint, record filter, row, label, kg per price unit, output unit)
# kg per price unit: 100 for "per 100 kg", 1000 for "per tonne"
SPECS = [
    # dairy (EUR/100kg)
    ("dairy/prices", {"product": "BUTTER"}, 331, "Butter", 100, "USD/kg"),
    ("dairy/prices", {"product": "SMP"}, 322, "Skimmed milk powder", 100, "USD/kg"),
    ("dairy/prices", {"product": "WMP"}, 323, "Whole milk powder", 100, "USD/kg"),
    ("dairy/prices", {"product": "WHEYPOWDER"}, 329, "Whey powder", 100, "USD/kg"),
    ("dairy/prices", {"product": "GOUDA"}, 338, "Gouda cheese", 100, "USD/kg"),
    ("dairy/prices", {"product": "CREAM"}, 321, "Cream", 100, "USD/kg"),
    ("rawMilk/prices", {"product": "Raw milk"}, 319, "Raw cow milk (farmgate)", 100, "USD/kg"),
    # oilseeds (EUR/t)
    ("oilseeds/prices", {"product": "Rapeseed meal"}, 734, "Rapeseed meal", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Crude soya bean oil"}, 647, "Crude soya bean oil", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Rapeseed"}, 593, "Rapeseed", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Soya beans"}, 587, "Soya beans", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Sunflower seed"}, 595, "Sunflower seed", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Soya meal"}, 729, "Soya meal", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Crude sunflower oil"}, 659, "Crude sunflower oil", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Sunflower seed meal"}, 733, "Sunflower seed meal", 1000, "USD/t"),
    ("oilseeds/prices", {"product": "Crude rape oil"}, 667, "Crude rapeseed oil", 1000, "USD/t"),
    # olive oil (EUR/100kg)
    ("oliveOil/prices", {"product": "Extra virgin olive oil (up to 0.8%)"}, 651, "Extra virgin olive oil", 100, "USD/kg"),
    ("oliveOil/prices", {"product": "Virgin olive oil (up to 2%)"}, 652, "Virgin olive oil", 100, "USD/kg"),
    ("oliveOil/prices", {"product": "Lampante olive oil (2%)"}, 653, "Lampante olive oil", 100, "USD/kg"),
    ("oliveOil/prices", {"product": "Refined olive oil (up to 0.3%)"}, 654, "Refined olive oil", 100, "USD/kg"),
    ("oliveOil/prices", {"product": "Crude olive-pomace oil (from 5 to 10%)"}, 655, "Crude olive-pomace oil", 100, "USD/kg"),
    ("oliveOil/prices", {"product": "Refined olive-pomace oil (up to 0.3%)"}, 656, "Refined olive-pomace oil", 100, "USD/kg"),
    # rice (EUR/t)
    ("rice/prices", {"stage": "Broken"}, 548, "Broken rice", 1000, "USD/t"),
    ("rice/prices", {"stage": "Milled non parboiled", "type": "Indica"}, 547, "Milled rice, Indica", 1000, "USD/t"),
    ("rice/prices", {"stage": "Paddy", "type": "Japonica"}, 545, "Paddy rice, Japonica", 1000, "USD/t"),
    # eggs, poultry, pig, beef, sheep (EUR/100kg)
    ("poultry/egg/prices", {"farmingMethod": "Barn"}, 341, "Eggs, barn (class A)", 100, "USD/kg"),
    ("poultry/prices", {"productName": "Whole broiler (65%)"}, 124, "Whole broiler 65%", 100, "USD/kg"),
    ("poultry/prices", {"productName": "Breast Fillet"}, 126, "Chicken breast fillet", 100, "USD/kg"),
    ("pigmeat/prices", {"pigClass": "Average S + E"}, 99, "Pig carcass S+E", 100, "USD/kg"),
    ("beef/prices", {"category": "Young bulls", "productCode": "AR3"}, 93, "Young bull carcass R3", 100, "USD/kg"),
    ("sheepAndGoat/prices", {"category": "Heavy Lamb"}, 105, "Heavy lamb carcass", 100, "USD/kg"),
    # cereals (EUR/t)
    ("cereal/prices", {"productName": "Milling wheat"}, 536, "Milling wheat", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Durum wheat"}, 534, "Durum wheat", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Feed barley"}, 540, "Feed barley", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Feed maize"}, 544, "Feed maize", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Feed oats"}, 542, "Feed oats", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Milling rye"}, 538, "Milling rye", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Grain sorghum"}, 550, "Grain sorghum", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Triticale"}, 557, "Triticale", 1000, "USD/t"),
    ("cereal/prices", {"productName": "Wheat bran"}, 723, "Wheat bran", 1000, "USD/t"),
]
# fruit & vegetables: variety prefix -> (row, label); ex-packaging station price, EUR/100kg
FV = {
    "Apples": (467, "Apples"), "Tomatoes": (353, "Tomatoes"), "Peaches": (473, "Peaches"),
    "Pears": (468, "Pears"), "Cucumbers": (366, "Cucumbers"), "Table Grapes": (462, "Table grapes"),
    "Garlic": (355, "Garlic"), "Bananas": (449, "Bananas (EU)"), "Oranges": (455, "Oranges"),
    "Onions": (354, "Onions"), "Cauliflowers": (357, "Cauliflowers"), "Peppers": (380, "Sweet peppers"),
    "Egg Plants": (371, "Aubergines"), "Plums": (474, "Plums"), "Carrots": (364, "Carrots"),
    "Ware potatoes": (352, "Ware potatoes"), "Melons": (465, "Melons"), "Lettuces": (360, "Lettuces"),
    "Cabbage": (358, "Cabbage"), "Water Melons": (464, "Watermelons"), "Courgettes": (384, "Courgettes"),
    "Beans": (368, "Beans"), "Lemons": (460, "Lemons"), "Strawberries": (475, "Strawberries"),
    "Leeks": (356, "Leeks"), "Apricots": (470, "Apricots"), "Mandarins": (456, "Mandarins"),
    "Kiwis": (479, "Kiwifruit"), "Cultivated Mushrooms": (373, "Cultivated mushrooms"),
}


def _num(s) -> float | None:
    if s is None:
        return None
    s = str(s).replace("€", "").strip()
    if re.fullmatch(r"[\d.]+,\d+", s):        # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _d(s):
    try:
        return dt.datetime.strptime(s, "%d/%m/%Y").date()
    except Exception:  # noqa: BLE001
        return None


def _get(s, path, params):
    r = s.get(f"{BASE}/{path}", params=params, timeout=90)
    r.raise_for_status()
    return r.json()


def _avg_latest(recs, label):
    """recs: list of dicts with price,endDate,memberStateCode. Returns (avg, end_date, n, countries)."""
    rows = []
    for x in recs:
        if x.get("memberStateCode") in NON_EURO:
            continue
        p = _num(x.get("price")); d = _d(x.get("endDate", "")) or _d(x.get("beginDate", ""))
        if p and p > 0 and d:
            rows.append((d, p, x.get("memberStateCode", "")))
    if not rows:
        return None
    last = max(r[0] for r in rows)
    sel = [r for r in rows if r[0] == last]
    eu = [r for r in sel if r[2] == "EU"]
    if eu:  # the Commission's own EU average takes precedence over a simple country mean
        sel = eu
    else:
        sel = [r for r in sel if r[2] != "EU"]
    return st.mean(r[1] for r in sel), last, len(sel), sorted({r[2] for r in sel})


def fetch(fx: dict) -> list[Price]:
    s = session()
    eur = fx.get("EUR")
    if not eur:
        return []
    today = dt.date.today()
    rng = {"beginDate": (today - dt.timedelta(days=45)).strftime("%d/%m/%Y"), "endDate": today.strftime("%d/%m/%Y")}
    cache: dict[str, list] = {}
    out: list[Price] = []

    def mk(row, label, avg, end, n, ctry, kg, unit, ep, extra=""):
        eur_per_kg = avg / kg
        usd = eur_per_kg * eur * (1000 if unit == "USD/t" else 1)
        per = "100 kg" if kg == 100 else "t"
        return Price(row=row, unit_usd=unit, price_type="EU market price, weekly average of euro-area Member States",
                     price_usd=usd, orig_price=round(avg, 2), orig_ccy="EUR", price_date=end.isoformat(),
                     source=f"European Commission Agri-food Data Portal - {label}{extra} ({n} reports: {','.join(ctry[:8])})",
                     link=LINK, calc=f"avg {avg:,.2f} EUR/{per} -> {eur_per_kg*(1000 if unit=='USD/t' else 1):,.4f} EUR/{unit.split('/')[1]} x {eur:.5f} EURUSD = {usd:,.4f} {unit}",
                     source_key="eu_agri")

    for ep, flt, row, label, kg, unit in SPECS:
        if ep not in cache:
            params = dict(rng)
            if ep.startswith("rawMilk"):
                params = {"years": f"{today.year - 1},{today.year}"}
            try:
                cache[ep] = _get(s, ep, params); polite_sleep(0.5)
            except Exception as e:  # noqa: BLE001
                log.warning("eu_agri %s: %s", ep, e); cache[ep] = []
        recs = [x for x in cache[ep] if all(str(x.get(k)) == v for k, v in flt.items())]
        res = _avg_latest(recs, label)
        if res:
            out.append(mk(row, label, *res, kg, unit, ep))
    # sugar: monthly EU average, EUR/t
    try:
        my = f"{today.year - 1}/{today.year}" if today.month < 10 else f"{today.year}/{today.year + 1}"
        sug = _get(s, "sugar/prices", {"marketingYears": f"{today.year - 1}/{today.year},{my}"})
        eu = [x for x in sug if x.get("sugarRegion") == "EU Average" and _num(x.get("price"))]
        if eu:
            x = max(eu, key=lambda r: r.get("ym", ""))
            y, m = map(int, x["ym"].split("/"))
            end = (dt.date(y, m, 28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
            p = Price(row=693, unit_usd="USD/t", price_type="EU white sugar market price, monthly EU average",
                      price_usd=_num(x["price"]) * eur, orig_price=round(_num(x["price"]), 2), orig_ccy="EUR",
                      price_date=end.isoformat(), source=f"European Commission sugar price reporting, EU average {x['ym']}",
                      link=LINK, calc=f"{_num(x['price']):,.2f} EUR/t x {eur:.5f} EURUSD = {_num(x['price'])*eur:,.2f} USD/t",
                      source_key="eu_agri")
            out.append(p)
    except Exception as e:  # noqa: BLE001
        log.warning("eu_agri sugar: %s", e)
    # fruit & vegetables
    try:
        fv = _get(s, "fruitAndVegetable/pricesSupplyChain",
                  {"beginDate": (today - dt.timedelta(days=30)).strftime("%d/%m/%Y"), "endDate": today.strftime("%d/%m/%Y")})
        for pref, (row, label) in FV.items():
            recs = [x for x in fv if x.get("productStage") == "Ex-packaging station price"
                    and re.split(r" [-–] ", x.get("variety", ""))[0] == pref
                    and ("All types" in x.get("variety", "") or "weighted average" in x.get("variety", ""))]
            res = _avg_latest(recs, label)
            if res:
                out.append(mk(row, label, *res, 100, "USD/kg", "fv", " (ex-packaging station)"))
    except Exception as e:  # noqa: BLE001
        log.warning("eu_agri F&V: %s", e)
    log.info("eu_agri: %d prices", len(out))
    return out
