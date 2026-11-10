import requests, json, csv, io
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderPriceProbe/1.0)"}
def t(name, url, params=None):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=60)
        print("==", name, r.status_code, len(r.content), r.url[:200]); return r
    except Exception as e:
        print("==", name, "ERR", str(e)[:150]); return None
for per in ("2026-08", "2026-07"):
    r = t("comext " + per, "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/ds-045409", {"freq": "M", "reporter": "EU27_2020", "partner": "ET", "product": "090111", "flow": "1", "indicators": "VALUE_IN_EUROS", "time": per, "format": "JSON"})
    if r is not None: print(r.text[:700])
r = t("comext2", "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/ds-045409", {"freq": "M", "reporter": "EU27_2020", "product": "090111", "flow": "1", "lastTimePeriod": "1", "format": "JSON"})
if r is not None: print(r.text[:1500])
for rep, nm in (("76", "Brazil"), ("231", "Ethiopia"), ("704", "Viet Nam"), ("764", "Thailand"), ("356", "India"), ("384", "Cote d'Ivoire")):
    for per in ("202608", "202606", "2025"):
        freq = "A" if len(per) == 4 else "M"
        r = t(f"comtrade {nm} {per}", f"https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS", {"reporterCode": rep, "cmdCode": "090111,100630,120740,180100,080131", "flowCode": "X", "period": per, "partnerCode": 0, "customsCode": "C00", "motCode": 0})
        if r is not None and not r.ok: print("   ", r.text[:200])
        if r is not None and r.ok:
            d = r.json().get("data", [])
            print("   rows", len(d), [(x.get("cmdCode"), x.get("period"), round((x.get("primaryValue") or 0) / (x.get("netWgt") or 1), 3), int(x.get("netWgt") or 0)) for x in d if x.get("partner2Code") in (0, None)][:6])
            if d: break
r = t("hdx wfp eth", "https://data.humdata.org/api/3/action/package_show", {"id": "wfp-food-prices-for-ethiopia"})
if r is not None and r.ok:
    res = r.json()["result"]["resources"]; print([(x["name"], x["url"][-70:]) for x in res][:4])
    c = t("wfp csv", res[0]["url"])
    if c is not None and c.ok:
        rows = list(csv.DictReader(io.StringIO(c.text))); print(len(rows), list(rows[0].keys()))
        last = max(x["date"] for x in rows[1:]); print("last", last)
        com = {}
        for x in rows[1:]:
            if x["date"] >= "2026-06": com.setdefault((x["commodity"], x["pricetype"], x["unit"]), []).append(float(x["usdprice"] or 0))
        for k, v in sorted(com.items())[:60]: print("  ", k, len(v), round(sum(v) / len(v), 3))
r = t("fpma", "https://fpma.fao.org/giews/v4/price_module/api/v1/FpmaSerie/", {"format": "json"})
if r is not None: print(r.text[:500])
