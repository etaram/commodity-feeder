"""Exchange rates from the ECB (free, official): daily reference rates against the euro, converted to USD per unit.
The margin model and quotes in other currencies read data/leads/fx.csv (date, currency, usd_per_unit, chg_30d_pct).
Run inside leads.run: python -m leads.fx
"""
import csv

from .common import LEADS, log, session

API = "https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A"
CURS = ["USD", "CNY", "INR", "TRY", "ILS", "GBP", "JPY", "KRW", "ZAR", "EGP", "AED", "SAR", "KES", "NGN", "BRL", "MXN", "VND", "IDR", "THB", "PLN"]


def series(s, cur):
    try:
        r = s.get(API.format(cur=cur), params={"lastNObservations": 25, "format": "csvdata"}, timeout=40)
        if r.status_code != 200:
            return []
        rows = list(csv.DictReader(r.text.splitlines()))
        return [(x["TIME_PERIOD"], float(x["OBS_VALUE"])) for x in rows if x.get("OBS_VALUE")]
    except Exception as e:  # noqa: BLE001
        log.warning("ecb fx %s: %s", cur, type(e).__name__); return []


def build():
    s = session()
    usd = series(s, "USD")  # USD per EUR
    if not usd:
        log.warning("ecb fx: no USD series"); return []
    out = [{"date": usd[-1][0], "currency": "EUR", "usd_per_unit": round(usd[-1][1], 5), "chg_30d_pct": round((usd[-1][1] / usd[0][1] - 1) * 100, 2)}]
    for cur in CURS[1:]:
        v = series(s, cur)  # cur per EUR
        if not v:
            continue
        last, first = usd[-1][1] / v[-1][1], usd[0][1] / v[0][1]
        out.append({"date": v[-1][0], "currency": cur, "usd_per_unit": round(last, 6), "chg_30d_pct": round((last / first - 1) * 100, 2)})
    with open(LEADS / "fx.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "currency", "usd_per_unit", "chg_30d_pct"]); w.writeheader(); w.writerows(out)
    log.info("ecb fx: %d currencies", len(out))
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print(build())
