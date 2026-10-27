"""FX: USD value of one unit of each currency.

Primary: Frankfurter (ECB reference rates, free, no key).
Fallback: open.er-api.com (free, no key).
"""
from __future__ import annotations

from .common import session, log

CCYS = ["EUR", "CNY", "CAD", "MYR", "JPY", "ILS", "GBP", "INR", "AUD", "BRL", "NOK", "CHF", "ZAR", "RUB", "KRW"]


def usd_per_unit() -> tuple[dict[str, float], str]:
    s = session()
    try:
        r = s.get("https://api.frankfurter.app/latest", params={"from": "USD"}, timeout=30)
        r.raise_for_status()
        j = r.json()
        rates = {k: 1.0 / v for k, v in j["rates"].items() if v}
        rates["USD"] = 1.0
        return rates, f"ECB via Frankfurter {j.get('date')}"
    except Exception as e:  # noqa: BLE001
        log.warning("frankfurter failed: %s", e)
    r = s.get("https://open.er-api.com/v6/latest/USD", timeout=30)
    r.raise_for_status()
    j = r.json()
    rates = {k: 1.0 / v for k, v in j["rates"].items() if v}
    rates["USD"] = 1.0
    return rates, f"open.er-api.com {j.get('time_last_update_utc', '')[:16]}"
