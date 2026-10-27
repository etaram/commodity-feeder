import csv
import datetime as dt
import json
import logging
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LEADS = DATA / "leads"
PARTIAL = LEADS / "partial"
log = logging.getLogger("leads")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,he;q=0.8"})
    return s


def cffi_get(url, **kw):
    from curl_cffi import requests as cr
    return cr.get(url, impersonate="chrome", timeout=60, **kw)


def today():
    return dt.date.today()


def clean(s, n=None):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:n] if n else s


def master_rows():
    return list(csv.DictReader(open(DATA / "master_rows.csv", encoding="utf-8")))


def benchmarks():
    """row -> (label, price, unit, source_key, date). Feed price, else the manual price kept in the sheet."""
    out = {}
    names = {int(r["row"]): r["name"] for r in master_rows()}
    for r in csv.DictReader(open(DATA / "prices.csv", encoding="utf-8")):
        if r.get("price_usd"):
            out[int(r["row"])] = (names.get(int(r["row"]), r["name"]), float(r["price_usd"]), r["unit_usd"],
                                  r["source_key"], r["price_date"])
    man = ROOT / "tools" / "manual_sources.csv"
    if man.exists():
        for r in csv.DictReader(open(man, encoding="utf-8")):
            row = int(r["row"])
            if row not in out and r.get("price"):
                try:
                    out[row] = (names.get(row, r["product"]), float(r["price"]), r["unit"], r["family"], r.get("date", ""))
                except ValueError:
                    pass
    return out


def fmt_bench(b):
    name, price, unit, key, date = b
    name = re.sub(r"\s+-\s+.*(futures|settlement).*$", "", name)
    return f"{clean(name, 60)}: {price:,.4g} {unit} ({key}, {date})"


def save_partial(name, rows, meta=None):
    PARTIAL.mkdir(parents=True, exist_ok=True)
    (PARTIAL / f"{name}.json").write_text(json.dumps({"source": name, "rows": rows, "meta": meta or {},
                                                      "ran": dt.datetime.utcnow().isoformat(timespec="minutes")},
                                                     ensure_ascii=False))


def polite(sec=2.5):
    time.sleep(sec)
