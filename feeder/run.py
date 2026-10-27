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
SOURCES = ["yahoo", "westmetall", "em_global", "cn_spot", "eu_agri", "dtn", "ssb", "scrapmonster", "smi",
           "census", "comext", "comtrade"]
DAILY = {"yahoo", "westmetall", "em_global", "cn_spot", "smi"}
CURRENT_WINDOW = 7
MASS = {"USD/kg": 1.0, "USD/t": 1000.0, "USD/oz": 1 / 32.1507466, "USD/lb": 1 / 2.20462}


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO); self.lines = []
    def emit(self, rec):
        self.lines.append(f"{rec.levelname} {rec.getMessage()}"[:300])


def _convert(p: Price, unit: str) -> None:
    """Re-express a mass-based price in another mass unit (kg, t, oz, lb), in place."""
    if p.unit_usd == unit or p.unit_usd not in MASS or unit not in MASS:
        return
    f = MASS[unit] / MASS[p.unit_usd]
    p.price_usd *= f
    p.calc += f" -> x {f:g} = {p.price_usd:,.4f} {unit}"
    p.unit_usd = unit
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
    cap = _Capture(); logging.getLogger().addHandler(cap)
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
        elif name == "eu_agri":
            from .sources import eu_agri; prices = eu_agri.fetch(rates)
        elif name == "dtn":
            from .sources import scrapers; prices = scrapers.dtn()
        elif name == "ssb":
            from .sources import scrapers; prices = scrapers.ssb_salmon(rates)
        elif name == "scrapmonster":
            from .sources import scrapers; prices = scrapers.scrapmonster()
        elif name == "smi":
            from .sources import scrapers; prices = scrapers.smi()
        elif name == "census":
            from .sources import census; prices = census.fetch(hs_idx)
        elif name == "comext":
            from .sources import comext; prices = comext.fetch(hs_idx, rates)
        elif name == "comtrade":
            from .sources import comtrade
            covered = set()
            for other in ("census", "comext", "cn_spot", "eu_agri", "scrapmonster", "dtn", "ssb"):
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
    report["newest_date"] = max((p.price_date for p in prices), default=None)
    report["log"] = cap.lines[-40:]
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

    from . import benchmark as bm
    for row in list(by):   # one unit per row before deriving/comparing
        ok = [c for c in by[row] if not c.quality.startswith("REJECTED")]
        if not ok:
            continue
        lead = min(ok, key=lambda c: (bm.TIER.get(c.source_key, 9), bm.INTRA.get(c.source_key, 9)))
        target = prev[row][1] if row in prev and prev[row][1] in MASS and lead.unit_usd in MASS else lead.unit_usd
        for c in ok:
            _convert(c, target)
    bm.derive(by)
    bmap = bm.load_map()
    today = dt.date.today()
    best = {}
    for row, cands in by.items():
        ok = [c for c in cands if not c.quality.startswith("REJECTED")]
        if not ok:
            continue
        m = by_row[row]
        b, chk, note = bm.select(row, ok, bmap, m, today)
        if chk is not None and chk.unit_usd != b.unit_usd:
            _convert(chk, b.unit_usd)
        notes = [] if b.quality == "OK" else [b.quality]
        b.tier = bm.TIER_LABEL.get(bm.TIER.get(b.source_key, 4), "")
        b.selection = note
        if chk is not None and chk.unit_usd == b.unit_usd and b.price_usd > 0:
            dev = chk.price_usd / b.price_usd - 1
            b.check_source = chk.source[:160]
            b.check_price = round(chk.price_usd, 6 if chk.price_usd < 1 else 4)
            b.deviation_pct = round(dev * 100, 1)
            if abs(dev) > 0.5 and bm.TIER.get(chk.source_key, 4) <= bm.TIER.get(b.source_key, 4) + 1:
                notes.append(f"CHECK: {chk.source_key} check price is {dev:+.0%} vs benchmark")
        pv = prev.get(row)
        if b.source_key in DAILY and pv and pv[1] == b.unit_usd and pv[0] > 0:
            ch = b.price_usd / pv[0] - 1
            if abs(ch) > 0.4:
                notes.append(f"CHECK: {ch:+.0%} vs previous feed price {pv[0]:.4g}")
        if note.startswith("FALLBACK"):
            notes.append(note)
        b.quality = "; ".join(notes) or "OK"
        b.id, b.hs6, b.name = m["id"], m["hs6"], m["name"]
        best[row] = b
    bm.save_map(bmap)

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
        "by_source_selected": {k: sum(1 for p in best.values() if p.source_key == k) for k in SOURCES + ["derived"]},
        "by_tier": {t: sum(1 for p in best.values() if p.tier == t) for t in sorted({p.tier for p in best.values()})},
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
