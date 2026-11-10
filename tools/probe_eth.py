import json, requests, time
from leads import origin_prices as o
j = o.get("https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/ds-045409?freq=M&reporter=EU27_2020&flow=1&product=090111&indicators=VALUE_IN_EUROS&indicators=QUANTITY_IN_100KG&lastTimePeriod=3&format=JSON").json()
print("ids", j.get("id"), "size", j.get("size"), "value type", type(j.get("value")).__name__, "n", len(j.get("value") or []))
for d in j["id"]:
    idx = j["dimension"][d]["category"]["index"]; print(d, type(idx).__name__, list(idx.items())[:6] if isinstance(idx, dict) else idx[:6])
rows = o._jsonstat(j); print("decoded", len(rows), rows[:4])
for label, params in (("multi-period", {"period": "202608,202607", "cmdCode": "090111,100630"}), ("44 codes", {"period": "202608", "cmdCode": ",".join(h for _, _, h in o.TRADED)}), ("22 codes", {"period": "202608", "cmdCode": ",".join(h for _, _, h in o.TRADED[:22])})):
    r = requests.get("https://comtradeapi.un.org/public/v1/preview/C/M/HS", params={"reporterCode": 76, "flowCode": "X", "partnerCode": 0, "customsCode": "C00", "motCode": 0, **params}, headers=o.UA, timeout=60)
    d = r.json().get("data", []) if r.ok else []
    print("comtrade", label, r.status_code, len(d), r.text[:160] if not d else [(x.get("cmdCode"), x.get("period"), x.get("netWgt"), x.get("qty"), x.get("qtyUnitCode"), x.get("altQty"), x.get("altQtyUnitCode"), int(x.get("primaryValue") or 0)) for x in d[:5]])
    time.sleep(3)
