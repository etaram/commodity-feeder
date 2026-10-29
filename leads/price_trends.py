"""Commodity price trends per commodity group, used as a factor in the deal calculation.

Source: World Bank Commodity Markets "Pink Sheet" historical monthly prices (official, free, CC-BY 4.0), refreshed
weekly into data/leads/price_trends.json, plus the live prices of the Commodities Tracker (data/prices.csv).
Run: python -m leads.price_trends
"""
import csv
import datetime as dt
import io
import json
import re

from .common import DATA, LEADS, log, session

OUT = LEADS / "price_trends.json"
PAGE = "https://www.worldbank.org/en/research/commodity-markets"
SERIES = {
    "FUEL": ["crude oil, average", "coal, australian", "natural gas, europe"],
    "GRAIN": ["wheat, us hrw", "maize", "rice, thai 5%"],
    "OILSEED": ["soybean oil", "palm oil", "soybeans"],
    "SOFTS": ["sugar, world", "coffee, arabica", "cocoa", "tea, avg"],
    "FEED": ["soybean meal"],
    "FERT": ["urea", "dap", "phosphate rock", "potassium chloride"],
    "STEEL": ["iron ore"],
    "NONFERROUS": ["aluminum", "copper", "zinc", "nickel"],
    "PRECIOUS": ["gold", "silver"],
    "MEAT": ["beef", "chicken"],
    "FISH": ["shrimps"],
    "WOODPAPER": ["sawnwood", "logs"],
    "TEXTILE": ["cotton"],
    "PLASTIC": ["rubber, tsr20"],
    "CHEM": ["crude oil, average"],  # proxy: petrochemical feedstock
}


def _xlsx_url():
    s = session()
    html = s.get(PAGE, timeout=60).text
    m = re.search(r'https?://[^"\']+CMO-Historical-Data-Monthly\.xlsx', html)
    return m.group(0) if m else None


def _monthly(url):
    import openpyxl
    raw = session().get(url, timeout=120).content
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb["Monthly Prices"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows[:12]) if r and any(isinstance(c, str) and "Crude oil" in c for c in r))
    names = [str(c or "").strip() for c in rows[hdr_i]]
    units = [str(c or "").strip() for c in rows[hdr_i + 1]]
    data = {}
    for r in rows[hdr_i + 1:]:
        if not r or not isinstance(r[0], str) or not re.match(r"^\d{4}M\d{2}$", r[0]):
            continue
        for j, v in enumerate(r[1:], 1):
            if isinstance(v, (int, float)) and j < len(names) and names[j]:
                data.setdefault(names[j], {})[r[0]] = float(v)
    return data, dict(zip(names, units))


def _chg(ser, months):
    keys = sorted(ser)
    if len(keys) <= months:
        return None
    a, b = ser[keys[-1 - months]], ser[keys[-1]]
    return round((b / a - 1) * 100, 1) if a else None


def build():
    url = _xlsx_url()
    if not url:
        log.warning("price trends: Pink Sheet link not found"); return None
    data, units = _monthly(url)
    low = {k.lower(): k for k in data}
    groups, series_out = {}, []
    for gid, keys in SERIES.items():
        ch = {1: [], 3: [], 12: []}
        for k in keys:
            name = next((v for lk, v in low.items() if lk.startswith(k)), None)
            if not name:
                continue
            ser = data[name]
            last = sorted(ser)[-1]
            row = {"group": gid, "series": name, "unit": units.get(name, ""), "month": last, "price": ser[last]}
            for m in ch:
                c = _chg(ser, m)
                row[f"chg_{m}m_pct"] = c
                if c is not None:
                    ch[m].append(c)
            series_out.append(row)
        if ch[3]:
            avg = {m: round(sum(v) / len(v), 1) if v else None for m, v in ch.items()}
            t3 = avg[3]
            signal = "rising fast" if t3 >= 8 else "rising" if t3 >= 3 else "falling fast" if t3 <= -8 else \
                "falling" if t3 <= -3 else "stable"
            groups[gid] = {"chg_1m_pct": avg[1], "chg_3m_pct": t3, "chg_12m_pct": avg[12], "signal": signal,
                           "series": ", ".join(s["series"] for s in series_out if s["group"] == gid)}
    out = {"source": url, "built": dt.date.today().isoformat(), "groups": groups, "series": series_out}
    OUT.write_text(json.dumps(out, indent=1))
    log.info("price trends: %d groups, %d series (%s)", len(groups), len(series_out), url)
    return out


def load(max_age_days=7):
    """Trends per group id; rebuilt when older than a week (falls back to the cached file)."""
    j = json.loads(OUT.read_text()) if OUT.exists() else None
    if not j or (dt.date.today() - dt.date.fromisoformat(j["built"])).days >= max_age_days:
        try:
            j = build() or j
        except Exception as e:  # noqa: BLE001
            log.warning("price trends refresh failed: %s", e)
    return (j or {}).get("groups", {}), (j or {}).get("series", [])


def tracker_rows():
    """Live Commodities Tracker prices (data/prices.csv) for the 'Commodity Prices' tab."""
    p = DATA / "prices.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if not r.get("price_usd"):
            continue
        out.append({"id": r["id"], "hs6": r["hs6"], "commodity": r["name"], "price_usd": r["price_usd"],
                    "unit": r["unit_usd"], "price_type": r["price_type"], "date": r["price_date"],
                    "source": r["source"], "quality": r["tier"], "link": r["link"]})
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(build()["groups"], indent=1))
