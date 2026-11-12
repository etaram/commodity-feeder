"""Award-proven suppliers: what the latest supplier build added, by source and region, and the queue that sends the new
ones to the website check and the enrichment first.

The supplier universe (leads/universe.py) reads every contract award notice the engine collects (TED, OCDS publishers,
World Bank, IDB, AIIB, USAspending, national portals). A winner with one recent award in a Sinder focus sector of
USD 100k or more is listed (tier 3) with the award as its evidence ('proven' column: contract, buyer, date, value,
source, link) and a role from the award and the name (manufacturer / trader / EPC; the website check confirms it).

This module only compares builds and writes the queue:
  snapshot  before the build: the keys and tiers of the current universe (data/private/proven_prev.json.gz)
  report    after the build: suppliers listed now that were not listed before (new key, or tier 4 before), per award
            source and region, weak regions highlighted; queue data/private/proven_queue.txt (name|country, best first)
            for leads/company_check.py and the enrichment priority list; counts only in data/leads/proven_report.json

  python -m leads.proven snapshot | report
"""
import csv
import datetime as dt
import gzip
import json
import re
import sys
from collections import Counter, defaultdict

from .common import LEADS, PRIVATE, log

PREV = PRIVATE / "proven_prev.json.gz"
STATE = PRIVATE / "proven_state.json"
QUEUE = PRIVATE / "proven_queue.txt"
REPORT = LEADS / "proven_report.json"
WEAK = ["Middle East & North Africa", "East Asia", "Sub-Saharan Africa", "Latin America"]
QUEUE_MAX = 5000


def _rows():
    p = PRIVATE / "universe.csv"
    if not p.exists():
        return
    csv.field_size_limit(10_000_000)
    with open(p, encoding="utf-8") as f:
        yield from csv.DictReader(f)


def snapshot():
    keys = {f"{r['supplier']}|{r['country']}": r.get("tier", "") for r in _rows()}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with gzip.open(PREV, "wt", encoding="utf-8") as f:
        json.dump(keys, f)
    log.info("proven snapshot: %d suppliers on record before the build", len(keys))
    return len(keys)


def source_of(proven):
    """The award source named in the evidence text: 'won: ... [TED https://...; TED-123]' -> 'TED'."""
    tail = (proven or "")[(proven or "").rfind("[") + 1:]
    m = re.match(r"([^\];]+?)(?: https?://[^\];]*)?;", tail)
    return (m.group(1).strip() if m else "") or "unknown"


def diff(prev, rows, today):
    """New listed proven suppliers (pure): rows with award evidence, listed now (tier 1-3), absent before or tier 4."""
    new = []
    for r in rows:
        if not r.get("proven") or r.get("tier") not in ("1", "2", "3") or r.get("dup_of"):
            continue
        k = f"{r['supplier']}|{r['country']}"
        before = prev.get(k)
        if before in ("1", "2", "3"):
            continue
        new.append({"key": k, "was": "absent" if before is None else f"tier {before}", "source": source_of(r["proven"]),
                    "region": r.get("region") or "unknown", "role": r.get("award_role") or "", "usd": float(r.get("proven_focus_usd") or 0),
                    "reach": bool(r.get("email") or r.get("phone") or r.get("website")), "sector": r.get("main_sector") or ""})
    return new


def summarise(new, today):
    by_src, by_reg, by_role, by_sec = Counter(), Counter(), Counter(), Counter()
    src_reg = defaultdict(Counter)
    for x in new:
        by_src[x["source"]] += 1; by_reg[x["region"]] += 1; by_role[x["role"]] += 1; by_sec[x["sector"] or "(none)"] += 1
        src_reg[x["source"]][x["region"]] += 1
    return {
        "at": today, "new_listed_proven": len(new),
        "was_absent": sum(1 for x in new if x["was"] == "absent"), "was_tier_4": sum(1 for x in new if x["was"] == "tier 4"),
        "without_contact_yet": sum(1 for x in new if not x["reach"]),
        "by_source": dict(by_src.most_common()), "by_region": dict(by_reg.most_common()),
        "weak_regions": {w: by_reg.get(w, 0) for w in WEAK},
        "by_role": dict(by_role.most_common()), "by_sector": dict(by_sec.most_common(15)),
        "source_by_region": {s: dict(c.most_common()) for s, c in sorted(src_reg.items(), key=lambda y: -sum(y[1].values()))[:25]},
    }


def queue_order(new):
    """Best first: weak regions and no contact yet (most to gain), then the size of the proving award."""
    return sorted(new, key=lambda x: (x["region"] not in WEAK, x["reach"], -x["usd"]))


def report():
    today = dt.date.today().isoformat()
    if not PREV.exists():
        log.warning("proven report: no snapshot from before the build - nothing to compare"); return {}
    with gzip.open(PREV, "rt", encoding="utf-8") as f:
        prev = json.load(f)
    rows = list(_rows())
    new = diff(prev, rows, today)
    rep = summarise(new, today)
    rep["listed_with_award_evidence"] = sum(1 for r in rows if r.get("proven") and r.get("tier") in ("1", "2", "3"))
    rep["promoted_rule"] = "one award in a focus sector within 730 days, USD 100k or more (leads/universe.py PROVEN_MIN_USD)"
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except ValueError:
            state = {}
    for x in new:
        state.setdefault(x["key"], today)
    STATE.write_text(json.dumps(state))
    # the queue keeps the earlier entries that are still waiting (newest first, then the older ones)
    old_q = QUEUE.read_text(encoding="utf-8").splitlines() if QUEUE.exists() else []
    q = list(dict.fromkeys([x["key"] for x in queue_order(new)] + old_q))[:QUEUE_MAX]
    QUEUE.write_text("\n".join(q) + "\n", encoding="utf-8")
    rep["queued_for_website_check_and_enrichment"] = len(q)
    REPORT.write_text(json.dumps(rep, indent=1, ensure_ascii=False))
    log.info("proven report: %d new listed proven suppliers (%d new keys, %d were tier 4), %d without contact; weak regions %s",
             rep["new_listed_proven"], rep["was_absent"], rep["was_tier_4"], rep["without_contact_yet"], rep["weak_regions"])
    log.info("proven by source: %s", json.dumps(dict(list(rep["by_source"].items())[:15])))
    log.info("proven by region: %s", json.dumps(rep["by_region"]))
    log.info("proven by role: %s", json.dumps(rep["by_role"]))
    return rep


def queued(limit=QUEUE_MAX):
    """name|country keys waiting for the website check (read by leads/company_check.py)."""
    if not QUEUE.exists():
        return []
    return [k for k in QUEUE.read_text(encoding="utf-8").splitlines() if "|" in k][:limit]


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    snapshot() if cmd == "snapshot" else report()
