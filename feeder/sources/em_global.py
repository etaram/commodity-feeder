"""Eastmoney international futures board (COMEX, NYMEX, CBOT, SGX, ICE, LME, Bursa, TOCOM) via AKShare.

Used for layer A contracts that Yahoo does not carry (LME base metals 3M, Bursa palm oil,
SGX iron ore, TOCOM/OSE rubber, ICE gasoil, Robusta, white sugar, canola).
The full board is saved to data/raw/em_global.csv so mappings can be audited.
"""
from __future__ import annotations

import datetime as dt

from ..common import Price, DATA, log, LB_PER_KG

# Eastmoney contract prefix -> (master row, Master unit, quote currency, multiplier to Master unit, label)
# For each prefix the contract with the largest open interest (持仓量) and a live price is used.
MAP: dict[str, tuple] = {
    "B": (2, "USD/bbl", "USD", 1, "ICE Brent"), "CL": (3, "USD/bbl", "USD", 1, "NYMEX WTI"),
    "NG": (5, "USD/MMBtu", "USD", 1, "NYMEX Henry Hub"), "RB": (8, "USD/gal", "USD", 1, "NYMEX RBOB"),
    "HO": (9, "USD/gal", "USD", 1, "NYMEX ULSD"), "G": (10, "USD/t", "USD", 1, "ICE Gasoil"),
    "NCF": (11, "USD/t", "USD", 1, "ICE Newcastle coal"),
    "GC": (17, "USD/oz", "USD", 1, "COMEX gold"), "SI": (18, "USD/oz", "USD", 1, "COMEX silver"),
    "PL": (19, "USD/oz", "USD", 1, "NYMEX platinum"), "PA": (20, "USD/oz", "USD", 1, "NYMEX palladium"),
    "ZW": (33, "USD/bu", "USc", 1, "CBOT wheat"), "ZC": (36, "USD/bu", "USc", 1, "CBOT corn"),
    "ZS": (37, "USD/bu", "USc", 1, "CBOT soybeans"), "ZM": (38, "USD/short ton", "USD", 1, "CBOT soybean meal"),
    "ZL": (39, "USD/lb", "USc", 1, "CBOT soybean oil"), "ZR": (40, "USD/cwt", "USD", 1, "CBOT rough rice"),
    "ZO": (41, "USD/bu", "USc", 1, "CBOT oats"), "MPM": (44, "USD/t", "MYR", 1, "Bursa crude palm oil"),
    "SB": (48, "USD/lb", "USc", 1, "ICE sugar No.11"), "CT": (50, "USD/lb", "USc", 1, "ICE cotton No.2"),
    "JRU": (57, "USD/kg", "JPY", 1, "OSE RSS3 rubber"),
}


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
    import re as _re
    df = df.copy()
    df["pre"] = df["代码"].astype(str).str.upper().str.replace(r"\d.*$", "", regex=True)
    df["oi"] = df["持仓量"].fillna(0)
    df = df[df["最新价"].notna()].sort_values("oi", ascending=False).drop_duplicates("pre")
    for _, x in df.iterrows():
        code = str(x.get("代码", "")).upper()
        if x["pre"] not in MAP:
            continue
        row, unit, ccy, mult, label = MAP[x["pre"]]
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
                         source=f"{label} {code} ({x.get('名称', '')}) via Eastmoney",
                         link="https://quote.eastmoney.com/center/gridlist.html#futures_global",
                         calc=f"{px} {ccy} x {rate:.6f}" + (f" x {mult:g}" if mult != 1 else "") + f" = {usd:.4f} {unit}",
                         source_key="em_global"))
    log.info("em_global: %d prices", len(out))
    return out
