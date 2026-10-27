"""Shared helpers: the Price record, an HTTP session with retries, and the master row list."""
from __future__ import annotations

import csv
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
log = logging.getLogger("feeder")

# Lower number = preferred when two sources give a price with the same date.
SOURCE_RANK = {
    # international exchange benchmarks first, then official market reporting, then dealer
    # assessments, then China domestic spot (VAT-inclusive), then monthly trade unit values
    "yahoo": 1,
    "westmetall": 2,
    "em_global": 2,
    "eu_agri": 3,
    "usda_mars": 3,
    "eia": 3,
    "dtn": 3,
    "ssb": 3,
    "scrapmonster": 4,
    "smi": 4,
    "cn_spot": 5,
    "census": 7,
    "comext": 8,
    "comtrade": 9,
}

FIELDS = [
    "row", "id", "hs6", "name",
    "unit_usd", "price_type", "price_usd", "orig_price", "orig_ccy",
    "price_date", "source", "link", "calc", "source_key", "quality",
    "tier", "selection", "check_source", "check_price", "deviation_pct",
    "designated_source", "benchmark_product", "mode",
]


@dataclass
class Price:
    row: int
    unit_usd: str          # e.g. USD/t, USD/kg, USD/bbl
    price_type: str        # e.g. "Futures (Yahoo, delayed)", "Trade unit value (US imports, Aug 2026)"
    price_usd: float
    orig_price: float
    orig_ccy: str
    price_date: str        # YYYY-MM-DD
    source: str            # human readable
    link: str
    calc: str              # the calculation, human readable
    source_key: str        # key into SOURCE_RANK
    id: str = ""
    hs6: str = ""
    name: str = ""
    quality: str = "OK"
    tier: str = ""
    selection: str = ""
    check_source: str = ""
    check_price: str = ""
    deviation_pct: str = ""

    def as_row(self) -> dict:
        d = asdict(self)
        d["price_usd"] = round(self.price_usd, 6 if self.price_usd < 1 else 4)
        return {k: d.get(k, "") for k in FIELDS}


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    return s


def load_master() -> list[dict]:
    with open(DATA / "master_rows.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["row"] = int(r["row"])
    return rows


def hs_index(master: list[dict]) -> dict[str, list[dict]]:
    """HS6 code -> master rows (only 6-digit search-layer rows)."""
    idx: dict[str, list[dict]] = {}
    for r in master:
        if r["layer"] == "SEARCH" and len(r["hs6"]) == 6:
            idx.setdefault(r["hs6"], []).append(r)
    return idx


def env(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None


def polite_sleep(sec: float = 1.0) -> None:
    time.sleep(sec)


# ---- unit helpers -------------------------------------------------------
LB_PER_KG = 2.20462
KG_PER_SHORT_TON = 907.185
KG_PER_LONG_TON = 1016.05
TROY_OZ_PER_KG = 32.1507
