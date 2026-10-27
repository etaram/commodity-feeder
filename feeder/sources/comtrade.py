"""UN Comtrade monthly import unit values (HS6), used only for rows the US/EU data did not cover.

With COMTRADE_KEY: data API (500 calls/day, 100k records/call).
Without a key: public preview endpoint (max 500 records per call).
Unit value = sum(primaryValue USD) / sum(netWgt kg) across several large importers.
"""
from __future__ import annotations

import datetime as dt

from ..common import Price, session, log, env, polite_sleep

KEYED = "https://comtradeapi.un.org/data/v1/get/C/M/HS"
PREVIEW = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
REPORTERS = "156,392,410,699,76"  # China, Japan, Korea, India, Brazil
BATCH = 20
MAX_CALLS = 120
MIN_VALUE_USD = 200_000


def _periods(n=5):
    d = dt.date.today().replace(day=1); out = []
    for _ in range(n):
        d = (d - dt.timedelta(days=1)).replace(day=1)
        out.append(d.strftime("%Y%m"))
    return out


def fetch(hs_idx: dict, wanted_codes: list[str]) -> list[Price]:
    if not wanted_codes:
        return []
    s = session(); key = env("COMTRADE_KEY")
    url = KEYED if key else PREVIEW
    if key:
        s.headers["Ocp-Apim-Subscription-Key"] = key
    calls = 0
    # find the latest period with data using a small probe
    period = None
    for p in _periods(6)[1:]:
        try:
            r = s.get(url, params={"reporterCode": REPORTERS, "period": p, "partnerCode": "0", "flowCode": "M",
                                   "cmdCode": "100199", "includeDesc": "false"}, timeout=60)
            calls += 1
            if r.ok and r.json().get("data"):
                period = p; break
        except Exception as e:  # noqa: BLE001
            log.info("comtrade probe %s: %s", p, e)
        polite_sleep(1.2)
    if not period:
        log.warning("comtrade: no period found")
        return []
    log.info("comtrade period %s (%s)", period, "key" if key else "preview")
    agg = {}
    for i in range(0, len(wanted_codes), BATCH):
        if calls >= MAX_CALLS:
            break
        codes = wanted_codes[i:i + BATCH]
        try:
            r = s.get(url, params={"reporterCode": REPORTERS, "period": period, "partnerCode": "0",
                                   "flowCode": "M", "cmdCode": ",".join(codes), "includeDesc": "false"},
                      timeout=90)
            calls += 1
            r.raise_for_status()
            for x in r.json().get("data") or []:
                c = str(x.get("cmdCode")); v = x.get("primaryValue") or 0; w = x.get("netWgt") or 0
                if c in hs_idx and v and w and w > 0:
                    agg.setdefault(c, []).append((str(x.get("reporterCode")), float(v), float(w)))
        except Exception as e:  # noqa: BLE001
            log.warning("comtrade batch %d: %s", i, e)
        polite_sleep(1.2)
    y, m = int(period[:4]), int(period[4:])
    pdate = ((dt.date(y, m, 28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)).isoformat()
    names = {"156": "CN", "392": "JP", "410": "KR", "699": "IN", "76": "BR"}
    out = []
    for c, recs in agg.items():
        recs = [r for r in recs if r[1] >= 50_000]          # ignore tiny, noisy flows
        v = sum(r[1] for r in recs); w = sum(r[2] for r in recs)
        if v < MIN_VALUE_USD or not recs:
            continue
        uvs = sorted(r[1] / r[2] for r in recs)
        mid = len(uvs) // 2
        uv = uvs[mid] if len(uvs) % 2 else (uvs[mid - 1] + uvs[mid]) / 2   # median across importers
        quality = "OK" if uvs[-1] / uvs[0] <= 5 else f"CHECK: importer unit values range {uvs[0]:.3g}-{uvs[-1]:.3g} USD/kg"
        per = ", ".join(f"{names.get(r[0], r[0])} {r[1]/r[2]:.3g}" for r in recs)
        unit = "USD/kg"; mult = 1
        if uv < 0.5:
            uv *= 1000; unit = "USD/t"; mult = 1000
        for r in hs_idx[c]:
            out.append(Price(
                row=r["row"], unit_usd=unit,
                price_type=f"Trade unit value (imports CN/JP/KR/IN/BR, {period[:4]}-{period[4:]})",
                price_usd=uv, orig_price=round(v, 0), orig_ccy="USD", price_date=pdate,
                source=f"UN Comtrade, HS {c}, imports of China, Japan, Korea, India, Brazil, {period}",
                link="https://comtradeplus.un.org/TradeFlow",
                calc=f"median of importer unit values (USD/kg: {per}) = {uv/mult:.4f} USD/kg" + (" x 1000" if mult > 1 else "") + f" = {uv:.4f} {unit}",
                source_key="comtrade", quality=quality))
    log.info("comtrade: %d prices, %d calls", len(out), calls)
    return out
