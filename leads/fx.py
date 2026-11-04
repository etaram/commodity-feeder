"""Exchange rates: ECB daily reference rates (against the euro, converted to USD per unit) and the Bank of Israel
representative rate for the shekel; every currency is also given in shekels per unit (ils_per_unit).
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


BOI_NOW = "https://boi.org.il/PublicApi/GetExchangeRates"
BOI_SDMX = "https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/EXR/1.0/RER_USD_ILS"


def boi_usd_ils(s):
    """Bank of Israel representative rate: shekels per US dollar, latest and about 30 days earlier."""
    try:
        r = s.get(BOI_NOW, timeout=30, headers={"Accept": "application/json"})
        now = next((x for x in (r.json().get("exchangeRates") or []) if x.get("key") == "USD"), None) if r.status_code == 200 else None
        last = float(now["currentExchangeRate"]) if now else None
        day = str(now.get("lastUpdate", ""))[:10] if now else ""
    except Exception as e:  # noqa: BLE001
        log.warning("boi fx now: %s", type(e).__name__); last, day = None, ""
    first = None
    try:
        import datetime as dt
        start = (dt.date.today() - dt.timedelta(days=32)).isoformat()
        r = s.get(BOI_SDMX, params={"startperiod": start, "format": "csv"}, timeout=40)
        if r.status_code == 200:
            rows = [x for x in csv.DictReader(r.text.splitlines()) if x.get("OBS_VALUE")]
            if rows:
                first = float(rows[0]["OBS_VALUE"])
                if last is None:
                    last, day = float(rows[-1]["OBS_VALUE"]), rows[-1].get("TIME_PERIOD", "")
    except Exception as e:  # noqa: BLE001
        log.warning("boi fx series: %s", type(e).__name__)
    return last, first, day


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
    # the shekel: Bank of Israel representative rate first (official for Israel), the ECB cross rate as a fallback
    ils_now, ils_then, ils_day = boi_usd_ils(s)
    ecb_ils = next((x for x in out if x["currency"] == "ILS"), None)
    if ils_now:
        usd_ils = 1 / ils_now
        chg = round((ils_then / ils_now - 1) * 100, 2) if ils_then else ""
        if ecb_ils:
            out.remove(ecb_ils)
        out.append({"date": ils_day or usd[-1][0], "currency": "ILS", "usd_per_unit": round(usd_ils, 6), "chg_30d_pct": chg, "source": "Bank of Israel"})
    out.append({"date": usd[-1][0], "currency": "USD", "usd_per_unit": 1, "chg_30d_pct": 0})
    # every currency also in shekels, and its 30-day move against the shekel
    ils = next((x for x in out if x["currency"] == "ILS"), None)
    for x in out:
        x.setdefault("source", "ECB")
        if ils:
            x["ils_per_unit"] = round(x["usd_per_unit"] / ils["usd_per_unit"], 5)
            a, b = x.get("chg_30d_pct"), ils.get("chg_30d_pct")
            x["chg_30d_vs_ils_pct"] = round(((1 + a / 100) / (1 + b / 100) - 1) * 100, 2) if a != "" and b not in ("", None) else ""
        else:
            x["ils_per_unit"], x["chg_30d_vs_ils_pct"] = "", ""
    with open(LEADS / "fx.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "currency", "usd_per_unit", "chg_30d_pct", "ils_per_unit", "chg_30d_vs_ils_pct", "source"]); w.writeheader(); w.writerows(out)
    log.info("ecb fx: %d currencies", len(out))
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print(build())
