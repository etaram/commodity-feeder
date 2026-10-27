"""Feed runner.

Each source runs in its own step and writes data/partial/<source>.json:
    python -m feeder.run --source census
Then the merge step selects the best price per Master row, validates it and writes the outputs:
    python -m feeder.run --merge

Selection per row: newest price date wins; on a tie the lower SOURCE_RANK wins.
Validation (column "quality"):
  * plausibility bounds per unit
  * cross-source disagreement (max/min > 3 among candidates of the same unit)
  * day-over-day jump > 40% vs the previous published price for daily sources
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import sys
import traceback

from .common import DATA, FIELDS, SOURCE_RANK, Price, load_master, hs_index, log
from . import fx as fxmod

PARTIAL = DATA / "partial"
SOURCES = ["yahoo", "westmetall", "em_global", "cn_spot", "census", "comext", "comtrade"]
DAILY = {"yahoo", "westmetall", "em_global", "cn_spot"}
BOUNDS = {"USD/kg": (0.001, 2_000_000), "USD/t": (1, 2_000_000), "USD/oz": (0.5, 20_000)}


def _fx():
    p = PARTIAL / "fx.json"
    if p.exists():
        j = json.loads(p.read_text())
        return j["rates"], j["source"]
    rates, src = fxmod.usd_per_unit()
    PARTIAL.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rates": rates, "source": src}))
    return rates, src


def _load_partial(name):
    p = PARTIAL / f"{name}.json"
    if not p.exists():
        return [], {"ok": False, "error": "no output"}
    j = json.loads(p.read_text())
    return [Price(**d) for d in j["prices"]], j["report"]


def run_source(name: str) -> int:
    master = load_master()
    by_row = {r["row"]: r for r in master}
    hs_idx = hs_index(master)
    rates, fx_src = _fx()
    log.info("FX: %s", fx_src)
    t0 = dt.datetime.utcnow()
    prices: list[Price] = []
    try:
        if name == "yahoo":
            from .sources import yahoo; prices = yahoo.fetch(by_row, rates)
        elif name == "westmetall":
            from .sources import westmetall; prices = westmetall.fetch()
        elif name == "em_global":
            from .sources import em_global; prices = em_global.fetch(rates)
        elif name == "cn_spot":
            from .sources import cn_spot; prices = cn_spot.fetch(rates)
        elif name == "census":
            from .sources import census; prices = census.fetch(hs_idx)
        elif name == "comext":
            from .sources import comext; prices = comext.fetch(hs_idx, rates)
        elif name == "comtrade":
            from .sources import comtrade
            covered = set()
            for other in ("census", "comext", "cn_spot"):
                covered |= {p.row for p in _load_partial(other)[0]}
            missing = sorted({c for c, rows in hs_idx.items() if any(r["row"] not in covered for r in rows)})
            log.info("comtrade: %d HS codes still missing", len(missing))
            prices = comtrade.fetch(hs_idx, missing)
        else:
            raise SystemExit(f"unknown source {name}")
        report = {"ok": True, "prices": len(prices)}
    except Exception as e:  # noqa: BLE001
        log.error("%s failed: %s", name, e)
        report = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}
    report["sec"] = (dt.datetime.utcnow() - t0).seconds
    PARTIAL.mkdir(parents=True, exist_ok=True)
    (PARTIAL / f"{name}.json").write_text(json.dumps(
        {"report": report, "prices": [p.__dict__ for p in prices]}, ensure_ascii=False))
    log.info("%s: %s", name, {k: v for k, v in report.items() if k != "trace"})
    return 0


def merge() -> int:
    master = load_master()
    by_row = {r["row"]: r for r in master}
    rates, fx_src = _fx()
    prev = {}
    if (DATA / "prices.csv").exists():
        with open(DATA / "prices.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    prev[int(r["row"])] = (float(r["price_usd"]), r["unit_usd"])
                except (ValueError, KeyError):
                    pass
    results, reports = [], {}
    for s in SOURCES:
        got, rep = _load_partial(s)
        results += got; reports[s] = rep

    by: dict[int, list[Price]] = {}
    for p in results:
        if p.row not in by_row or not p.price_usd or p.price_usd <= 0:
            continue
        lo, hi = BOUNDS.get(p.unit_usd, (1e-6, 1e9))
        if not lo <= p.price_usd <= hi:
            p.quality = f"REJECTED: {p.price_usd:.4g} {p.unit_usd} outside plausible range"
        by.setdefault(p.row, []).append(p)

    best = {}
    for row, cands in by.items():
        ok = [c for c in cands if not c.quality.startswith("REJECTED")]
        if not ok:
            continue
        b = max(ok, key=lambda c: (c.price_date, -SOURCE_RANK.get(c.source_key, 99)))
        same = [c.price_usd for c in ok if c.unit_usd == b.unit_usd]
        notes = [] if b.quality == "OK" else [b.quality]
        if len(same) >= 2 and max(same) / min(same) > 3:
            others = ", ".join(f"{c.source_key} {c.price_usd:.4g}" for c in ok if c is not b and c.unit_usd == b.unit_usd)
            notes.append(f"CHECK: sources disagree >3x ({others})")
        pv = prev.get(row)
        if b.source_key in DAILY and pv and pv[1] == b.unit_usd and pv[0] > 0:
            ch = b.price_usd / pv[0] - 1
            if abs(ch) > 0.4:
                notes.append(f"CHECK: {ch:+.0%} vs previous feed price {pv[0]:.4g}")
        b.quality = "; ".join(notes) or "OK"
        m = by_row[row]; b.id, b.hs6, b.name = m["id"], m["hs6"], m["name"]
        best[row] = b

    with open(DATA / "prices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        for row in sorted(best):
            w.writerow(best[row].as_row())
    with open(DATA / "candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        for row in sorted(by):
            for p in by[row]:
                m = by_row[row]; p.id, p.hs6, p.name = m["id"], m["hs6"], m["name"]
                w.writerow(p.as_row())
    summary = {
        "finished_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
        "fx_source": fx_src, "fx": {k: rates[k] for k in fxmod.CCYS + ["USD"] if k in rates},
        "sources": reports, "rows_with_price": len(best), "candidates": len(results),
        "flagged": sum(1 for b in best.values() if b.quality != "OK"),
        "by_source_selected": {k: sum(1 for p in best.values() if p.source_key == k) for k in SOURCES},
    }
    (DATA / "run_log.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    log.info("merge: %d rows, %d flagged", len(best), summary["flagged"])
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args(argv)
    if a.merge:
        return merge()
    if a.source:
        return run_source(a.source)
    for s in SOURCES:
        run_source(s)
    return merge()


if __name__ == "__main__":
    sys.exit(main())
