"""Run every source, keep the best price per Master row, write data/prices.csv and data/run_log.json.

Selection per row: the most recent price date wins; on a tie the lower SOURCE_RANK wins.
Usage: python -m feeder.run [--only yahoo,census,...]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import sys
import traceback

from .common import DATA, FIELDS, SOURCE_RANK, load_master, hs_index, log
from . import fx as fxmod
from .sources import yahoo, census, comext, comtrade, cn_spot, westmetall

ALL = ["yahoo", "westmetall", "cn_spot", "census", "comext", "comtrade"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    only = [x for x in a.only.split(",") if x] or ALL
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

    started = dt.datetime.utcnow()
    master = load_master()
    by_row = {r["row"]: r for r in master}
    hs_idx = hs_index(master)
    rates, fx_src = fxmod.usd_per_unit()
    log.info("FX source: %s", fx_src)

    results, report = [], {}

    def run(name, fn, *args):
        if name not in only:
            return []
        t0 = dt.datetime.utcnow()
        try:
            got = fn(*args)
            report[name] = {"ok": True, "prices": len(got), "sec": (dt.datetime.utcnow() - t0).seconds}
            return got
        except Exception as e:  # noqa: BLE001
            log.error("%s failed: %s", name, e)
            report[name] = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}
            return []

    results += run("yahoo", yahoo.fetch, by_row, rates)
    results += run("westmetall", westmetall.fetch)
    results += run("cn_spot", cn_spot.fetch, rates)
    results += run("census", census.fetch, hs_idx)
    results += run("comext", comext.fetch, hs_idx, rates)
    covered = {p.row for p in results}
    missing_codes = sorted({c for c, rows in hs_idx.items() if any(r["row"] not in covered for r in rows)})
    results += run("comtrade", comtrade.fetch, hs_idx, missing_codes)

    best = {}
    for p in results:
        if p.row not in by_row or p.price_usd is None or p.price_usd <= 0:
            continue
        cur = best.get(p.row)
        key = (p.price_date, -SOURCE_RANK.get(p.source_key, 99))
        if cur is None or key > (cur.price_date, -SOURCE_RANK.get(cur.source_key, 99)):
            best[p.row] = p
    for row, p in best.items():
        m = by_row[row]; p.id = m["id"]; p.hs6 = m["hs6"]; p.name = m["name"]

    DATA.mkdir(exist_ok=True)
    with open(DATA / "prices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in sorted(best):
            w.writerow(best[row].as_row())
    # all candidates too, for audit
    with open(DATA / "candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for p in sorted(results, key=lambda x: (x.row, x.source_key)):
            m = by_row.get(p.row, {}); p.id = m.get("id", ""); p.hs6 = m.get("hs6", ""); p.name = m.get("name", "")
            w.writerow(p.as_row())
    summary = {
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
        "fx_source": fx_src, "fx": {k: rates[k] for k in fxmod.CCYS + ["USD"] if k in rates},
        "sources": report, "rows_with_price": len(best), "candidates": len(results),
        "by_source_selected": {k: sum(1 for p in best.values() if p.source_key == k) for k in ALL},
    }
    (DATA / "run_log.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    log.info("done: %s", json.dumps({k: v for k, v in summary.items() if k not in ("fx",)}, default=str)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
