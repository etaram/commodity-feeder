"""Scout scrapers: HTML pages that publish commodity prices in tables.

Each scraper returns Price records and also reports items it saw but has no mapping for
(data/raw/unmapped_<name>.csv) so new items can be added to the Master over time.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re

import pandas as pd

from ..common import Price, DATA, session, log, polite_sleep, LB_PER_KG


def _tables(url: str) -> list[pd.DataFrame]:
    r = session().get(url, timeout=60)
    r.raise_for_status()
    return pd.read_html(io.StringIO(r.text))


def _num(x) -> float | None:
    s = re.sub(r"[^\d.\-]", "", str(x).replace(",", ""))
    try:
        return float(s)
    except ValueError:
        return None


def _save_unmapped(name: str, rows: list[dict]) -> None:
    (DATA / "raw").mkdir(exist_ok=True)
    if not rows:
        return
    with open(DATA / "raw" / f"unmapped_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


# ---------------------------------------------------------------- ScrapMonster / IREM minor metals
SM_URL = "https://www.scrapmonster.com/metal-prices/minor-metals"
# (commodity name prefix, origin) -> master row
SM_MAP = {
    ("Bismuth ingot 99.99% min", "EXW China"): 1969,
    ("Cadmium Ingot 99.99% min", "EXW China"): 1998,
    ("Chrome Conc. SA 42% min", "CIF China"): 837,
    ("Chromic anhydrides 99.8% min", "EXW China"): 935,
    ("Chromium Oxide Green 99% min", "EXW China"): 936,
    ("Chromium Metal 99% min", "EXW China"): 1987,
    ("Magnesium Powder 99.9% min", "EXW China"): 1964,
    ("Magnesium Alloy AZ91D", "EXW China"): 1962,
    ("Magnesium Ingot 99.95% min", "EXW China"): 1961,
    ("Manganese dioxides Alkaline 91% min", "EXW China"): 937,
    ("Manganese Flake 99.7% min", "EXW China"): 1983,
    ("Molybdenum Powder 99.95% min", "EXW China"): 1951,
    ("Molybdenum bar 99.9% min", "EXW China"): 1953,
    ("Molybdenum oxides 57% min", "Port India"): 841,
    ("Tellurium Metal 99.99% min", "EXW China"): 915,
    ("Titanium dioxides R TiO2 93% min", "EXW China"): 939,
    ("Titanium plate TA2 2mm", "EXW China"): 1973,
    ("Titanium Sponge 99.7% min", "EXW China"): 1971,
    ("Tungsten Powder 99.95% min", "EXW China"): 1946,
    ("Tungsten bar W-4 99.9% min", "EXW China"): 1947,
    ("Tungsten ore WO3 65% min", "EXW China"): 838,
    ("Tungsten Scrap Drills 70% min", "Ex-VAT Delivered China"): 1949,
    ("Zirconium sponge Zr + Hf 99.4% min", "EXW China"): 1975,
    ("Zircon Sand Australian Zr (Hf) O2 66% min", "Port China"): 844,
    ("Ilmenite Conc Mozambican TiO2 52% min", "CIF China"): 843,
    ("Spodumene Li2O 6% min", "CIF China"): 825,
    ("Selenium Powder 99.9% min", "Delivered China"): 920,
    ("Arsenic Metal 99% min", "EXW China"): 919,
    ("Tantalum Metal 99.95% min", "Delivered US"): 1957,
    ("Antimony Ingot 99.65% min", "EXW China"): 1980,
    ("Cobalt Metal 99.8% min", "Delivered China"): 1966,
    ("Gallium metal 99.99% min", "EXW China"): 1999,
    ("Lithium Carbonates 99.5% min", "CIF China"): 960,
    ("Silicon Metal 5-5-3", "FOB China"): 917,
}


def _to_usd(price: float, unit: str):
    u = unit.strip().lower()
    if u in ("usd/mt", "usd/ton", "usd/t"):
        return price, "USD/t", f"{price} {unit}"
    if u == "usd/kg":
        return price, "USD/kg", f"{price} USD/kg"
    if u == "usd/lb":
        v = price * LB_PER_KG
        return v, "USD/kg", f"{price} USD/lb x 2.20462 = {v:.4f} USD/kg"
    return None, None, None


def scrapmonster() -> list[Price]:
    tables = _tables(SM_URL)
    df = pd.concat([t for t in tables if {"Commodity", "Origin", "Price", "Unit", "Date"} <= set(t.columns)])
    df["d"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values("d", ascending=False).drop_duplicates(["Commodity", "Origin"])
    out, unmapped, used = [], [], set()
    for _, x in df.iterrows():
        name, origin = str(x["Commodity"]), str(x["Origin"])
        row = next((r for (p, o), r in SM_MAP.items() if name.startswith(p) and origin == o), None)
        if row is None:
            unmapped.append({"commodity": name, "origin": origin, "price": x["Price"], "unit": x["Unit"], "date": x["Date"]})
            continue
        px = _num(x["Price"]); d = x["d"]
        if not px or pd.isna(d):
            continue
        usd, unit, calc = _to_usd(px, str(x["Unit"]))
        if usd is None:
            continue
        used.add(row)
        out.append(Price(row=row, unit_usd=unit, price_type="Spot assessment (IREM, weekly/irregular)",
                         price_usd=usd, orig_price=px, orig_ccy="USD", price_date=d.date().isoformat(),
                         source=f"ScrapMonster / Institute for Rare Earths and Metals - {name}, {origin}",
                         link=SM_URL, calc=calc + (f" = {usd:,.4f} {unit}" if "=" not in calc else ""),
                         source_key="scrapmonster"))
    _save_unmapped("scrapmonster", unmapped)
    log.info("scrapmonster: %d prices, %d unmapped items", len(out), len(unmapped))
    return out


# ---------------------------------------------------------------- Strategic Metals Invest
SMI_URL = "https://strategicmetalsinvest.com/current-strategic-metals-prices/"
SMI_MAP = {"Hafnium": 1990, "Rhenium": 1992, "Antimony": 1980, "Bismuth": 1969, "Tellurium": 915}


def smi() -> list[Price]:
    r = session().get(SMI_URL, timeout=60); r.raise_for_status()
    m = re.search(r"Last updated[^0-9A-Za-z]*([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4})", r.text)
    d = pd.to_datetime(m.group(1), errors="coerce").date() if m else dt.date.today()
    t = pd.read_html(io.StringIO(r.text))[0]
    out, unmapped = [], []
    for _, x in t.iterrows():
        metal = str(x.iloc[0]).strip(); px = _num(x.iloc[1])
        if not px:
            continue
        if metal not in SMI_MAP:
            unmapped.append({"metal": metal, "usd_per_kg": px}); continue
        out.append(Price(row=SMI_MAP[metal], unit_usd="USD/kg", price_type="Reference price (dealer, daily)",
                         price_usd=px, orig_price=px, orig_ccy="USD", price_date=d.isoformat(),
                         source=f"Strategic Metals Invest - {metal}", link=SMI_URL,
                         calc=f"{px} USD/kg as quoted (purity not stated by source)", source_key="smi"))
    _save_unmapped("smi", unmapped)
    log.info("smi: %d prices (as of %s)", len(out), d)
    return out


# ---------------------------------------------------------------- DTN retail fertilizer (weekly)
DTN_LISTS = ["https://www.dtnpf.com/agriculture/web/ag/crops",
             "https://www.dtnpf.com/agriculture/web/ag/news/crops"]
DTN_MAP = {"DAP": 1095, "MAP": 1096, "POTASH": 1090, "UREA": 1078, "10-34-0": 1100, "ANHYD": 925, "UAN32": 1085}
DTN_LABEL = {"DAP": "DAP", "MAP": "MAP", "POTASH": "Potash", "UREA": "Urea", "10-34-0": "10-34-0",
             "ANHYD": "Anhydrous ammonia", "UAN32": "UAN32"}


def dtn() -> list[Price]:
    s = session(); links = set()
    for u in DTN_LISTS:
        try:
            html = s.get(u, timeout=60).text
            links |= set(re.findall(r'href="(/agriculture/web/ag/[^"]*/article/(\d{4}/\d{2}/\d{2})/[^"]*fertilizer[^"]*)"', html, re.I))
        except Exception as e:  # noqa: BLE001
            log.warning("dtn list %s: %s", u, e)
    for path, _ in sorted(links, key=lambda x: x[1], reverse=True)[:4]:
        url = "https://www.dtnpf.com" + path
        try:
            t = pd.read_html(io.StringIO(s.get(url, timeout=60).text))[0]
        except Exception:  # noqa: BLE001
            continue
        out = []; header = None; latest = {}
        for _, x in t.iterrows():
            vals = [str(v) for v in x.values]
            if vals[0] == "Date Range":
                header = vals; continue
            if header and re.match(r"[A-Z][a-z]{2}", vals[0]):
                for i in range(1, len(vals)):
                    v = _num(vals[i])
                    if header[i] in DTN_MAP and v:
                        latest[header[i]] = (vals[0], v)   # rows are chronological: last one wins
        for k, (rng, v) in latest.items():
            m = re.search(r"(\w{3}) (\d+)-(?:(\w{3}) )?(\d+) (\d{4})", rng)
            end = dt.datetime.strptime(f"{m.group(3) or m.group(1)} {m.group(4)} {m.group(5)}", "%b %d %Y").date() if m else dt.date.today()
            usd = v / 0.907185
            out.append(Price(row=DTN_MAP[k], unit_usd="USD/t", price_type=f"US retail average, weekly survey ({rng})",
                             price_usd=usd, orig_price=v, orig_ccy="USD", price_date=end.isoformat(),
                             source=f"DTN Retail Fertilizer Trends - {DTN_LABEL[k]}", link=url,
                             calc=f"{v} USD/short ton / 0.907185 = {usd:,.2f} USD/t", source_key="dtn"))
        if out:
            log.info("dtn: %d prices from %s", len(out), url)
            return out
    log.warning("dtn: no table found")
    return []



# ---------------------------------------------------------------- Statistics Norway: salmon export price (weekly)
SSB_URL = "https://data.ssb.no/api/v0/en/table/03024"


def ssb_salmon(fx: dict) -> list[Price]:
    nok = fx.get("NOK")
    if not nok:
        return []
    q = {"query": [{"code": "VareGrupper2", "selection": {"filter": "item", "values": ["01", "02"]}},
                   {"code": "ContentsCode", "selection": {"filter": "item", "values": ["Kilopris"]}},
                   {"code": "Tid", "selection": {"filter": "top", "values": ["1"]}}],
         "response": {"format": "json-stat2"}}
    r = session().post(SSB_URL, json=q, timeout=60); r.raise_for_status()
    j = r.json()
    week = list(j["dimension"]["Tid"]["category"]["index"].keys())[0]
    vals = j["value"]
    y, w = int(week[:4]), int(week[5:])
    end = dt.date.fromisocalendar(y, w, 7)
    out = []
    for i, (row, label) in enumerate([(161, "fresh or chilled"), (206, "frozen")]):
        v = vals[i]
        if not v:
            continue
        usd = v * nok
        out.append(Price(row=row, unit_usd="USD/kg", price_type=f"Export price, weekly ({week})",
                         price_usd=usd, orig_price=v, orig_ccy="NOK", price_date=end.isoformat(),
                         source=f"Statistics Norway table 03024 - farmed salmon {label}, export price",
                         link="https://www.ssb.no/en/statbank1/table/03024/",
                         calc=f"{v} NOK/kg x {nok:.5f} NOKUSD = {usd:.4f} USD/kg", source_key="ssb"))
    log.info("ssb_salmon: %d prices (%s)", len(out), week)
    return out
