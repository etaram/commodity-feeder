"""Layer A: exchange futures from the Yahoo Finance chart endpoint (the same data yfinance uses).

Unofficial, free, no key. Prices are front-month futures, delayed ~10-20 min.
"""
from __future__ import annotations

import datetime as dt

from ..common import Price, session, log, polite_sleep, LB_PER_KG, KG_PER_SHORT_TON

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
URL2 = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}"

# Contracts quoted in US cents on the exchange (Yahoo currency "USX").
CENTS = {"ZW=F", "KE=F", "ZC=F", "ZS=F", "ZL=F", "ZO=F", "KC=F", "SB=F", "CT=F", "OJ=F",
         "LE=F", "GF=F", "HE=F"}

# master row -> (ticker, unit in Master, multiplier from (USD per quote unit) to (USD per Master unit), note)
MAP = {
    2: ("BZ=F", "USD/bbl", 1, ""),
    3: ("CL=F", "USD/bbl", 1, ""),
    5: ("NG=F", "USD/MMBtu", 1, ""),
    6: ("TTF=F", "USD/MWh", 1, "EUR->USD"),
    7: ("JKM=F", "USD/MMBtu", 1, ""),
    8: ("RB=F", "USD/gal", 1, ""),
    9: ("HO=F", "USD/gal", 1, ""),
    11: ("MTF=F", "USD/t", 1, ""),
    13: ("B0=F", "USD/gal", 1, ""),
    15: ("UX=F", "USD/lb", 1, ""),
    17: ("GC=F", "USD/oz", 1, ""),
    18: ("SI=F", "USD/oz", 1, ""),
    19: ("PL=F", "USD/oz", 1, ""),
    20: ("PA=F", "USD/oz", 1, ""),
    21: ("HG=F", "USD/t", LB_PER_KG * 1000, "USD/lb x 2,204.62 lb/t"),
    31: ("HRC=F", "USD/t", 1000 / KG_PER_SHORT_TON, "USD/short ton / 0.907185"),
    33: ("ZW=F", "USD/bu", 1, ""),
    34: ("KE=F", "USD/bu", 1, ""),
    36: ("ZC=F", "USD/bu", 1, ""),
    37: ("ZS=F", "USD/bu", 1, ""),
    38: ("ZM=F", "USD/short ton", 1, ""),
    39: ("ZL=F", "USD/lb", 1, ""),
    40: ("ZR=F", "USD/cwt", 1, ""),
    41: ("ZO=F", "USD/bu", 1, ""),
    45: ("KC=F", "USD/lb", 1, ""),
    47: ("CC=F", "USD/t", 1, ""),
    48: ("SB=F", "USD/lb", 1, ""),
    50: ("CT=F", "USD/lb", 1, ""),
    51: ("OJ=F", "USD/lb", 1, ""),
    52: ("LBR=F", "USD/1000 bf", 1, ""),
    53: ("LE=F", "USD/lb", 1, ""),
    54: ("GF=F", "USD/lb", 1, ""),
    55: ("HE=F", "USD/lb", 1, ""),
    56: ("DC=F", "USD/cwt", 1, ""),
}


def _quote(s, sym):
    for base in (URL, URL2):
        try:
            r = s.get(base.format(sym=sym), params={"range": "5d", "interval": "1d"}, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            res = r.json()["chart"]["result"]
            if res:
                return res[0]["meta"]
        except Exception as e:  # noqa: BLE001
            log.warning("yahoo %s via %s: %s", sym, base[:20], e)
            polite_sleep(2)
    return None


def fetch(master_by_row: dict, fx: dict) -> list[Price]:
    s = session()
    out: list[Price] = []
    for row, (sym, unit, mult, note) in MAP.items():
        meta = _quote(s, sym)
        polite_sleep(0.7)
        if not meta or meta.get("regularMarketPrice") is None:
            log.info("yahoo: no data for %s", sym)
            continue
        px = float(meta["regularMarketPrice"])
        ccy = meta.get("currency") or "USD"
        steps = []
        usd = px
        if sym in CENTS or ccy in ("USX", "USd"):
            usd = px / 100.0
            steps.append(f"{px} USc / 100")
            ccy_shown = "USc"
        elif ccy != "USD":
            rate = fx.get(ccy.upper())
            if not rate:
                log.warning("yahoo: no FX for %s (%s)", ccy, sym)
                continue
            usd = px * rate
            steps.append(f"{px} {ccy} x {rate:.6f} {ccy}USD")
            ccy_shown = ccy
        else:
            ccy_shown = "USD"
            steps.append(f"{px} USD")
        if mult != 1:
            usd *= mult
            steps.append(note or f"x {mult}")
        ts = meta.get("regularMarketTime")
        date = dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else dt.date.today().isoformat()
        out.append(Price(
            row=row, unit_usd=unit, price_type="Futures front month (Yahoo, delayed)",
            price_usd=usd, orig_price=px, orig_ccy=ccy_shown, price_date=date,
            source=f"Yahoo Finance {sym} ({meta.get('exchangeName', '')})",
            link=f"https://finance.yahoo.com/quote/{sym}",
            calc=" ; ".join(steps) + f" = {usd:.4f} {unit}", source_key="yahoo"))
    log.info("yahoo: %d prices", len(out))
    return out
