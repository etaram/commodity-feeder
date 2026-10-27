"""China domestic spot prices for exchange-listed commodities (100ppi / 生意社 via AKShare).

ak.futures_spot_price(date) returns the daily spot price that 100ppi publishes for each
commodity listed on SHFE / DCE / ZCE / GFEX / INE, alongside the futures price.
Prices are in CNY per tonne unless noted, VAT-inclusive domestic spot.
"""
from __future__ import annotations

import datetime as dt

from ..common import Price, log

# symbol -> (master row, label, CNY-quote unit -> tonnes factor)
#   factor converts "CNY per quote unit" into "CNY per tonne"
MAP = {
    "CU": (1857, "Copper cathode", 1), "AL": (1905, "Aluminium ingot", 1), "ZN": (1932, "Zinc ingot", 1),
    "PB": (1924, "Lead ingot", 1), "NI": (1890, "Nickel cathode", 1), "SN": (1941, "Tin ingot", 1),
    "RB": (1775, "Rebar HRB400", 1), "HC": (1754, "Hot-rolled coil", 1), "SS": (1803, "Stainless steel 304 CR", 1),
    "WR": (1772, "Wire rod", 1), "I": (826, "Iron ore (China port spot)", 1), "J": (870, "Metallurgical coke", 1),
    "JM": (864, "Coking coal", 1), "ZC": (865, "Thermal coal", 1), "SA": (955, "Soda ash", 1),
    "UR": (1078, "Urea", 1), "MA": (997, "Methanol", 1), "TA": (1074, "PTA", 1), "EG": (1006, "MEG", 1),
    "PP": (1153, "Polypropylene", 1), "L": (1148, "LLDPE", 1), "V": (1162, "PVC", 1),
    "EB": (993, "Styrene", 1), "BU": (900, "Bitumen", 1), "FU": (884, "Fuel oil", 1),
    "RU": (1217, "Natural rubber", 1), "NR": (1218, "TSR20 rubber", 1), "SP": (1373, "Bleached softwood kraft pulp", 1),
    "CF": (1482, "Cotton 3128B", 1), "SR": (693, "White sugar", 1), "A": (587, "Soybean No.1", 1),
    "M": (729, "Soybean meal", 1), "Y": (647, "Soybean oil", 1), "P": (658, "Palm olein 24", 1),
    "OI": (668, "Rapeseed oil", 1), "RM": (734, "Rapeseed meal", 1), "C": (544, "Corn", 1),
    "CS": (580, "Corn starch", 1), "JD": (341, "Eggs", 2), "AP": (467, "Apples", 1), "PK": (590, "Peanuts", 1),
    "LH": (70, "Live hogs", 1), "SF": (1716, "Ferrosilicon", 1), "SM": (1718, "Silicomanganese", 1),
    "SI": (917, "Industrial silicon 553", 1), "LC": (960, "Lithium carbonate", 1), "PG": (889, "LPG", 1),
    "SH": (927, "Caustic soda", 1), "PX": (991, "Paraxylene", 1), "PF": (1607, "Polyester staple fibre", 1),
    "BR": (1223, "Butadiene rubber", 1), "AO": (933, "Alumina", 1),
    "AU": (1679, "Gold", 1_000_000), "AG": (1675, "Silver", 1000),
}
# rows that are quoted per kg in USD in the Master (precious metals stay per kg there)
PER_KG = {1679, 1675}


def fetch(fx: dict) -> list[Price]:
    try:
        import akshare as ak
    except Exception as e:  # noqa: BLE001
        log.warning("akshare missing: %s", e)
        return []
    cny = fx.get("CNY")
    if not cny:
        return []
    df = None; used = None
    for back in range(0, 8):
        d = dt.date.today() - dt.timedelta(days=back)
        if d.weekday() >= 5:
            continue
        try:
            df = ak.futures_spot_price(d.strftime("%Y%m%d"))
            if df is not None and len(df):
                used = d; break
        except Exception as e:  # noqa: BLE001
            log.info("cn_spot %s: %s", d, e)
    if df is None or not len(df):
        log.warning("cn_spot: no data")
        return []
    out = []
    for _, x in df.iterrows():
        sym = str(x.get("symbol", "")).upper()
        if sym not in MAP:
            continue
        row, label, factor = MAP[sym]
        try:
            px = float(x["spot_price"])
        except (TypeError, ValueError, KeyError):
            continue
        if px <= 0:
            continue
        cny_t = px * factor
        if row in PER_KG:
            usd = cny_t / 1000 * cny; unit = "USD/kg"
            calc = f"{px} CNY/{'g' if sym == 'AU' else 'kg'} x {factor/1000:g} = {cny_t/1000:,.2f} CNY/kg x {cny:.6f} CNYUSD = {usd:,.2f} USD/kg"
        else:
            usd = cny_t * cny; unit = "USD/t"
            pre = f"{px} CNY/500kg x 2 = {cny_t:,.0f} CNY/t ; " if factor == 2 else f"{px} CNY/t ; "
            calc = pre + f"x {cny:.6f} CNYUSD = {usd:,.2f} USD/t"
        out.append(Price(
            row=row, unit_usd=unit, price_type="Spot (China domestic, daily, incl. VAT)",
            price_usd=usd, orig_price=px, orig_ccy="CNY", price_date=used.isoformat(),
            source=f"100ppi (生意社) spot via AKShare - {label} [{sym}]",
            link="https://www.100ppi.com/sf/", calc=calc, source_key="cn_spot"))
    log.info("cn_spot: %d prices (%s)", len(out), used)
    return out
