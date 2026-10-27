"""Eurostat Comext: EU monthly trade unit values by HS6 (extra-EU imports).

Dataset DS-045409 "EU trade since 1988 by HS2-4-6 and CN8". Free, no key.
Unit value = VALUE_IN_EUROS / (QUANTITY_IN_100KG * 100) -> EUR/kg -> USD/kg.
The API is SDMX/JSON-stat; dimension codes are tried in a few known variants.
"""
from __future__ import annotations

import datetime as dt

from ..common import Price, session, log, polite_sleep

BASE = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/{ds}"
VARIANTS = [
    # (dataset, reporter, partner, value indicator, quantity indicator, kg per qty unit)
    ("DS-045409", "EU", "EXT_EU", "VALUE_IN_EUROS", "QUANTITY_IN_100KG", 100.0),
    ("DS-045409", "EU27_2020", "EXT_EU27_2020", "VALUE_IN_EUROS", "QUANTITY_IN_100KG", 100.0),
    ("DS-059341", "EU", "EXT_EU", "VALUE_EUR", "QUANTITY_KG", 1.0),
    ("DS-059341", "EU27_2020", "EXT_EU27_2020", "VALUE_EUR", "QUANTITY_KG", 1.0),
]
BATCH = 40
MIN_VALUE_EUR = 200_000


def _jsonstat(j: dict) -> dict:
    """Return {(product, indicator, time): value} from a JSON-stat 2.0 dataset."""
    ids = j["id"]; size = j["size"]; dims = j["dimension"]
    pos = {}
    for d in ids:
        idx = dims[d]["category"]["index"]
        inv = {v: k for k, v in idx.items()} if isinstance(idx, dict) else dict(enumerate(idx))
        pos[d] = inv
    out = {}
    vals = j.get("value", {})
    items = vals.items() if isinstance(vals, dict) else enumerate(vals)
    for flat, v in items:
        if v is None:
            continue
        flat = int(flat); coords = {}
        for d, n in zip(reversed(ids), reversed(size)):
            coords[d] = pos[d][flat % n]; flat //= n
        out[(coords.get("product"), coords.get("indicators"), coords.get("time"))] = float(v)
    return out


def _query(s, var, products):
    ds, rep, par, vi, qi, _ = var
    params = [("format", "JSON"), ("lang", "en"), ("freq", "M"), ("reporter", rep), ("partner", par),
              ("flow", "1"), ("indicators", vi), ("indicators", qi), ("lastTimePeriod", "3")]
    params += [("product", p) for p in products]
    r = s.get(BASE.format(ds=ds), params=params, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    return _jsonstat(r.json())


def fetch(hs_idx: dict, fx: dict, skip_rows: set[int] | None = None) -> list[Price]:
    s = session()
    codes = sorted(hs_idx)
    eurusd = fx.get("EUR")
    if not eurusd:
        return []
    var = None
    for v in VARIANTS:  # find a variant that answers
        try:
            if _query(s, v, codes[:5]):
                var = v; break
        except Exception as e:  # noqa: BLE001
            log.info("comext variant %s failed: %s", v[:3], e)
    if not var:
        log.warning("comext: no working variant")
        return []
    log.info("comext using %s", var[:3])
    ds, rep, par, vi, qi, kgmult = var
    data = {}
    for i in range(0, len(codes), BATCH):
        try:
            data.update(_query(s, var, codes[i:i + BATCH]))
        except Exception as e:  # noqa: BLE001
            log.warning("comext batch %d: %s", i, e)
        polite_sleep(1)
    out = []
    for code in codes:
        times = sorted({t for (p, ind, t) in data if p == code}, reverse=True)
        v = q = 0.0; used = []
        for t in times:
            val = data.get((code, vi, t)); qty = data.get((code, qi, t))
            if not val or not qty:
                continue
            v += val; q += qty * kgmult; used.append(t)
            if v >= MIN_VALUE_EUR:
                break
        if not used or q <= 0:
            continue
        eur_kg = v / q
        usd = eur_kg * eurusd; unit = "USD/kg"; qshow = f"{q:,.0f} kg"
        if usd < 0.5:
            usd *= 1000; unit = "USD/t"; qshow = f"{q/1000:,.1f} t"
        period = used[0] if len(used) == 1 else f"{used[-1]}..{used[0]}"
        try:
            y, m = used[0].replace("M", "-").split("-")[:2]
            d0 = dt.date(int(y), int(m), 1)
            d1 = (d0.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
            pdate = d1.isoformat()
        except Exception:  # noqa: BLE001
            pdate = dt.date.today().isoformat()
        for r in hs_idx[code]:
            if skip_rows and r["row"] in skip_rows:
                continue
            out.append(Price(
                row=r["row"], unit_usd=unit, price_type=f"Trade unit value (EU extra-EU imports, {period})",
                price_usd=usd, orig_price=round(eur_kg, 4), orig_ccy="EUR",
                price_date=pdate, source=f"Eurostat Comext {ds}, HS {code}, {period}",
                link="https://ec.europa.eu/eurostat/comext/newxtweb/",
                calc=f"{v:,.0f} EUR / {qshow} = {eur_kg:.4f} EUR/kg x {eurusd:.5f} EURUSD = {usd:.4f} {unit}",
                source_key="comext"))
    log.info("comext: %d prices", len(out))
    return out
