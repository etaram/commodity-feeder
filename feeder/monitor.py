"""Source monitor ("scout watch").

Runs after the merge step and writes data/source_health.csv / .json:
  * every feed source: status, number of prices vs expected, newest data date, age, last log lines
  * every watched page (sources the scheduled search uses but the feed does not scrape yet):
    HTTP status, latency and whether the published data changed since the previous run

Status values:
  OK        - working, enough prices, fresh
  DEGRADED  - working but far fewer prices than expected or than last run (page/API structure may have changed)
  STALE     - newest data older than the allowed age for that source
  DOWN      - error, HTTP failure or zero prices
  CHANGED   - (watched pages) content changed since last run: new data to pick up
  UNCHANGED - (watched pages) reachable, no change
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import time

import pandas as pd

from .common import DATA, session, log

# feed source -> (expected minimum prices, max age in days, homepage)
FEED = {
    "yahoo": (25, 4, "https://finance.yahoo.com/markets/commodities/"),
    "westmetall": (6, 5, "https://www.westmetall.com/en/markdaten.php"),
    "em_global": (15, 4, "https://quote.eastmoney.com/center/gridlist.html#futures_global"),
    "cn_spot": (45, 6, "https://www.100ppi.com/sf/"),
    "eu_agri": (50, 21, "https://agridata.ec.europa.eu/extensions/DataPortal/prices.html"),
    "dtn": (7, 14, "https://www.dtnpf.com/agriculture/web/ag/crops"),
    "ssb": (2, 21, "https://www.ssb.no/en/statbank1/table/03024/"),
    "scrapmonster": (30, 45, "https://www.scrapmonster.com/metal-prices/minor-metals"),
    "smi": (5, 5, "https://strategicmetalsinvest.com/current-strategic-metals-prices/"),
    "usda": (20, 35, "https://www.ams.usda.gov/market-news"),
    "census": (800, 120, "https://api.census.gov/data/timeseries/intltrade/imports/hs"),
    "comext": (800, 120, "https://ec.europa.eu/eurostat/comext/newxtweb/"),
    "comtrade": (300, 150, "https://comtradeplus.un.org/"),
}
# pages to watch for new releases (used by the scheduled active search)
WATCH = {
    "World Bank Pink Sheet": "https://www.worldbank.org/en/research/commodity-markets",
    "China NBS 10-day prices": "https://www.stats.gov.cn/english/PressRelease/",
    "ICO coffee prices": "https://ico.org/resources/public-market-information/",
    "FAO Food Price Index": "https://www.fao.org/worldfoodsituation/foodpricesindex/en/",
    "Global Dairy Trade": "https://www.globaldairytrade.info/en/product-results/",
    "USDA FV shipping point": "https://www.ams.usda.gov/mnreports/fvwtrds.pdf",
    "USDA feedstuffs AMS_3668": "https://www.ams.usda.gov/mnreports/ams_3668.pdf",
    "USDA boxed beef AMS_2461": "https://www.ams.usda.gov/mnreports/ams_2461.pdf",
    "IMF primary commodity prices": "https://www.imf.org/en/Research/commodity-prices",
    "LME homepage": "https://www.lme.com/",
    "Spices Board India": "https://www.indianspices.com/marketing/price/domestic/current-market-price.html",
    "MPOB palm oil": "https://bepi.mpob.gov.my/",
}


def _signature(content: bytes, ctype: str) -> str:
    """Hash of the data part of a page: table cells when there are tables, else digits in the text."""
    if "pdf" in ctype or content[:4] == b"%PDF":
        return hashlib.sha1(content).hexdigest()[:16]
    text = content.decode("utf-8", "ignore")
    try:
        tables = pd.read_html(io.StringIO(text))
        return hashlib.sha1("|".join(t.to_csv(index=False) for t in tables).encode()).hexdigest()[:16]
    except Exception:  # noqa: BLE001
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        nums = re.findall(r"\d[\d.,]{2,}", text)
        return hashlib.sha1(" ".join(nums).encode()).hexdigest()[:16]


def main() -> int:
    now = dt.datetime.utcnow()
    prev = {}
    pj = DATA / "source_health.json"
    if pj.exists():
        try:
            prev = {r["source"]: r for r in json.loads(pj.read_text())["rows"]}
        except Exception:  # noqa: BLE001
            prev = {}
    rows = []
    for name, (exp, max_age, url) in FEED.items():
        p = DATA / "partial" / f"{name}.json"
        rep = json.loads(p.read_text())["report"] if p.exists() else {"ok": False, "error": "did not run"}
        n = rep.get("prices", 0) if rep.get("ok") else 0
        newest = rep.get("newest_date")
        age = (now.date() - dt.date.fromisoformat(newest)).days if newest else None
        last_n = (prev.get(name) or {}).get("prices") or 0
        if not rep.get("ok") or n == 0:
            status = "DOWN"
        elif n < exp * 0.5 or (last_n and n < last_n * 0.5):
            status = "DEGRADED"
        elif age is not None and age > max_age:
            status = "STALE"
        else:
            status = "OK"
        msg = rep.get("error") or ""
        warn = [l for l in rep.get("log", []) if l.startswith(("WARNING", "ERROR"))]
        if warn and not msg:
            msg = " | ".join(warn[-3:])
        rows.append({"source": name, "type": "feed", "status": status, "prices": n, "expected_min": exp,
                     "previous_prices": last_n, "newest_date": newest or "", "age_days": "" if age is None else age,
                     "max_age_days": max_age, "http_status": "", "latency_ms": rep.get("sec", 0) * 1000,
                     "changed": "", "last_change_utc": "", "message": msg[:400], "url": url})
    s = session()
    for name, url in WATCH.items():
        t0 = time.time(); code = ""; sig = ""; msg = ""
        try:
            r = s.get(url, timeout=45)
            code = r.status_code
            if r.ok:
                sig = _signature(r.content, r.headers.get("content-type", ""))
            else:
                msg = r.text[:150]
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"[:200]
        ms = int((time.time() - t0) * 1000)
        old = prev.get(name) or {}
        changed = bool(sig and old.get("signature") and sig != old.get("signature"))
        status = "DOWN" if code != 200 else ("CHANGED" if changed else ("UNCHANGED" if old.get("signature") else "OK"))
        rows.append({"source": name, "type": "watch", "status": status, "prices": "", "expected_min": "",
                     "previous_prices": "", "newest_date": "", "age_days": "", "max_age_days": "",
                     "http_status": code, "latency_ms": ms, "changed": "yes" if changed else "",
                     "last_change_utc": now.isoformat(timespec="minutes") if changed else old.get("last_change_utc", ""),
                     "message": msg, "url": url, "signature": sig or old.get("signature", "")})
    fields = ["source", "type", "status", "prices", "expected_min", "previous_prices", "newest_date", "age_days",
              "max_age_days", "http_status", "latency_ms", "changed", "last_change_utc", "message", "url"]
    with open(DATA / "source_health.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    pj.write_text(json.dumps({"checked_utc": now.isoformat(timespec="seconds"), "rows": rows}, indent=1, ensure_ascii=False))
    bad = [r["source"] for r in rows if r["status"] in ("DOWN", "DEGRADED", "STALE")]
    log.info("monitor: %d sources checked, attention: %s", len(rows), ", ".join(bad) or "none")
    return 0


if __name__ == "__main__":
    import logging, sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    sys.exit(main())
