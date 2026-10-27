"""LME official cash-settlement prices (USD/t), as republished daily by Westmetall."""
from __future__ import annotations

import io
import re
import datetime as dt

import pandas as pd

from ..common import Price, session, log, polite_sleep

URL = "https://www.westmetall.com/en/markdaten.php?action=table&field={f}"
MAP = {21: ("LME_Cu_cash", "Copper"), 22: ("LME_Al_cash", "Aluminium"), 23: ("LME_Zn_cash", "Zinc"),
       24: ("LME_Ni_cash", "Nickel"), 25: ("LME_Pb_cash", "Lead"), 26: ("LME_Sn_cash", "Tin")}


def _num(x) -> float | None:
    s = re.sub(r"[^\d.,]", "", str(x))
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def fetch() -> list[Price]:
    s = session()
    out = []
    for row, (field, metal) in MAP.items():
        url = URL.format(f=field)
        try:
            r = s.get(url, timeout=60); r.raise_for_status()
            tables = pd.read_html(io.StringIO(r.text))
        except Exception as e:  # noqa: BLE001
            log.warning("westmetall %s: %s", field, e); continue
        polite_sleep(1)
        got = False
        for t in tables:
            for _, x in t.iterrows():
                vals = list(x.values)
                try:
                    d = pd.to_datetime(str(vals[0]), dayfirst=True, errors="raise").date()
                except Exception:  # noqa: BLE001
                    continue
                px = _num(vals[1])
                if not px:
                    continue
                out.append(Price(
                    row=row, unit_usd="USD/t", price_type="LME official cash settlement (daily)",
                    price_usd=px, orig_price=px, orig_ccy="USD", price_date=d.isoformat(),
                    source=f"LME {metal} cash-settlement via Westmetall", link=url,
                    calc=f"{px} USD/t as published", source_key="westmetall"))
                got = True
                break
            if got:
                break
        if not got:
            log.warning("westmetall: could not parse %s", field)
    log.info("westmetall: %d prices", len(out))
    return out
