"""Eastmoney international futures board (COMEX, NYMEX, CBOT, SGX, ICE, LME, Bursa, TOCOM) via AKShare.

Used for layer A contracts that Yahoo does not carry (LME base metals 3M, Bursa palm oil,
SGX iron ore, TOCOM/OSE rubber, ICE gasoil, Robusta, white sugar, canola).
The full board is saved to data/raw/em_global.csv so mappings can be audited.
"""
from __future__ import annotations

import datetime as dt

from ..common import Price, DATA, log, LB_PER_KG

# Eastmoney code -> (master row, Master unit, quote currency, multiplier to Master unit, label)
# Codes are matched case-insensitively against the 代码 column; filled after inspecting the raw board.
MAP: dict[str, tuple] = {}


def fetch(fx: dict) -> list[Price]:
    try:
        import akshare as ak
    except Exception as e:  # noqa: BLE001
        log.warning("akshare missing: %s", e)
        return []
    df = ak.futures_global_spot_em()
    (DATA / "raw").mkdir(exist_ok=True)
    df.to_csv(DATA / "raw" / "em_global.csv", index=False, encoding="utf-8")
    log.info("em_global board: %d rows", len(df))
    out = []
    today = dt.date.today().isoformat()
    for _, x in df.iterrows():
        code = str(x.get("代码", "")).upper()
        if code not in MAP:
            continue
        row, unit, ccy, mult, label = MAP[code]
        try:
            px = float(x["最新价"])
        except (TypeError, ValueError, KeyError):
            continue
        if px <= 0:
            continue
        rate = 1.0 if ccy == "USD" else (0.01 if ccy == "USc" else fx.get(ccy))
        if not rate:
            continue
        usd = px * rate * mult
        out.append(Price(row=row, unit_usd=unit, price_type="Futures (exchange, Eastmoney board)",
                         price_usd=usd, orig_price=px, orig_ccy=ccy, price_date=today,
                         source=f"Eastmoney intl futures {code} - {label}",
                         link="https://quote.eastmoney.com/center/gridlist.html#futures_global",
                         calc=f"{px} {ccy} x {rate:.6f}" + (f" x {mult:g}" if mult != 1 else "") + f" = {usd:.4f} {unit}",
                         source_key="em_global"))
    log.info("em_global: %d prices", len(out))
    return out
