"""US Census Bureau international trade API: monthly import unit values by HS6.

Unit value = general imports value (USD, customs value) / quantity, aggregated from HS10 lines
that share the dominant unit of quantity within each HS6. Free; key optional (CENSUS_KEY).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from ..common import Price, session, log, env

URL = "https://api.census.gov/data/timeseries/intltrade/imports/hs"
LINK = "https://api.census.gov/data/timeseries/intltrade/imports/hs"

# Census unit code -> (multiplier to the base unit, base unit label)
UNITS = {
    "KG": (1, "kg"), "T": (1000, "kg"), "G": (0.001, "kg"), "GM": (0.001, "kg"),
    "CKG": (1, "kg"), "CGM": (0.001, "kg"), "CTN": (1000, "kg"), "CYK": (1, "kg"),
    "NO": (1, "unit"), "PCS": (1, "unit"), "DOZ": (12, "unit"), "DZ": (12, "unit"),
    "GR": (144, "unit"), "THS": (1000, "unit"), "HUN": (100, "unit"),
    "PRS": (1, "pair"), "DPR": (12, "pair"),
    "L": (1, "L"), "LTR": (1, "L"), "PFL": (1, "L pf"), "KL": (1000, "L"),
    "M": (1, "m"), "LNM": (1, "m"), "M2": (1, "m2"), "CM2": (0.0001, "m2"), "M3": (1, "m3"),
    "BBL": (1, "bbl"), "MWH": (1, "MWh"), "CAR": (1, "carat"), "KTS": (1, "carat"),
}
MIN_VALUE_USD = 200_000  # below this a month's unit value is too noisy; widen the window


def _months_back(n: int) -> list[str]:
    d = dt.date.today().replace(day=1)
    out = []
    for _ in range(n):
        d = (d - dt.timedelta(days=1)).replace(day=1)
        out.append(d.strftime("%Y-%m"))
    return out


def _get_month(s, month: str, key: str | None):
    params = {"get": "I_COMMODITY,GEN_VAL_MO,GEN_QY1_MO,UNIT_QY1", "COMM_LVL": "HS10", "time": month}
    if key:
        params["key"] = key
    r = s.get(URL, params=params, timeout=180)
    if r.status_code == 204 or not r.text.strip():
        return None
    r.raise_for_status()
    rows = r.json()
    head = rows[0]
    return [dict(zip(head, x)) for x in rows[1:]]


def fetch(hs_idx: dict) -> list[Price]:
    s = session()
    key = env("CENSUS_KEY")
    # find the latest published month, then also pull the two before it
    data = {}
    for m in _months_back(6):
        try:
            rows = _get_month(s, m, key)
        except Exception as e:  # noqa: BLE001
            log.warning("census %s: %s", m, e)
            rows = None
        if rows:
            data[m] = rows
            if len(data) == 3:
                break
        elif data:
            break
    if not data:
        log.warning("census: no data")
        return []
    months = sorted(data, reverse=True)
    log.info("census months: %s", months)

    # agg[hs6][month][unit] = [value, qty_in_base]
    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0])))
    for m, rows in data.items():
        for x in rows:
            code = (x.get("I_COMMODITY") or "")[:6]
            if code not in hs_idx:
                continue
            u = (x.get("UNIT_QY1") or "").strip().upper()
            if u not in UNITS:
                continue
            try:
                v = float(x["GEN_VAL_MO"]); q = float(x["GEN_QY1_MO"])
            except (TypeError, ValueError):
                continue
            if v <= 0 or q <= 0:
                continue
            mult, base = UNITS[u]
            a = agg[code][m][base]
            a[0] += v
            a[1] += q * mult

    out = []
    for code, by_month in agg.items():
        # dominant base unit by total value
        tot = defaultdict(float)
        for m in by_month:
            for base, (v, _) in by_month[m].items():
                tot[base] += v
        base = max(tot, key=tot.get)
        latest = months[0]
        used = []
        v = q = 0.0
        for m in months:  # widen window until value is meaningful
            if base in by_month.get(m, {}):
                v += by_month[m][base][0]; q += by_month[m][base][1]; used.append(m)
            if v >= MIN_VALUE_USD:
                break
        if q <= 0 or v <= 0:
            continue
        uv = v / q
        unit = f"USD/{base}"
        if base == "kg" and uv < 0.5:  # bulk goods read better per tonne
            uv *= 1000; unit = "USD/t"; qshow = q / 1000; qunit = "t"
        else:
            qshow = q; qunit = base
        period = used[0] if len(used) == 1 else f"{used[-1]}..{used[0]}"
        last = dt.date.fromisoformat(used[0] + "-01")
        month_end = (last.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        for r in hs_idx[code]:
            out.append(Price(
                row=r["row"], unit_usd=unit,
                price_type=f"Trade unit value (US imports, {period})",
                price_usd=uv, orig_price=round(v, 0), orig_ccy="USD",
                price_date=month_end.isoformat(),
                source=f"US Census Bureau, imports HS {code}, {period}",
                link=f"{LINK}?get=I_COMMODITY,GEN_VAL_MO,GEN_QY1_MO,UNIT_QY1&COMM_LVL=HS10&time={used[0]}",
                calc=f"{v:,.0f} USD / {qshow:,.1f} {qunit} = {uv:.4f} {unit}",
                source_key="census"))
    log.info("census: %d prices", len(out))
    return out
