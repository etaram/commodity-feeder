"""Source quality, separate from source health: a collector that ran is not proof that its notices are fresh,
complete, unique or useful. Per source (as named on the notices) this measures, over the open-notice sheet:

  open       open notices listed
  fresh_7d   share first seen in the last run window (new flag) - how much the source is still bringing
  deadline   share with a deadline; value: share with a value; buyer: share with a buyer; title_en: share translated
  expired    notices still listed after their deadline (should be 0)
  dup_in     share duplicated inside the source (same title, buyer and country)
  mirrored   share also published by another source (counted once, not as independent confirmation)
  goods      share the deal engine marks Pursue or Watch (useful to Sinder at all)

Flags: thin parse (deadline or buyer under 50%), duplicates over 15%, expired notices listed, nothing new.
Writes data/leads/source_quality.csv. Run after the merge: python -m leads.source_quality
"""
import csv
import glob
import re
from collections import defaultdict

from .common import LEADS, log

KEY = re.compile(r"[^a-z0-9]+")


def _k(r):
    return (KEY.sub(" ", (r.get("title_en") or r.get("title_original") or "").lower()).strip()[:90],
            KEY.sub(" ", (r.get("buyer") or "").lower()).strip()[:60], (r.get("country") or "")[:3])


def main():
    rows = []
    for f in sorted(glob.glob(str(LEADS / "sheet" / "tenders_[0-9][0-9].csv"))):
        rows += list(csv.DictReader(open(f, encoding="utf-8")))
    by_src, keys_src = defaultdict(list), defaultdict(set)
    for r in rows:
        s = r.get("source") or "(unknown)"
        by_src[s].append(r)
        k = _k(r)
        if k[0]:
            keys_src[k].add(s)
    out = []
    for s, rs in by_src.items():
        n = len(rs)
        pct = lambda c: round(100 * c / n) if n else 0  # noqa: E731
        seen, dup = set(), 0
        for r in rs:
            k = _k(r)
            if k in seen:
                dup += 1
            seen.add(k)
        mirrored = sum(1 for k in seen if len(keys_src.get(k, ())) > 1)

        def days(r):
            try:
                return float(r.get("days_left"))
            except (TypeError, ValueError):
                return None
        expired = sum(1 for r in rs if (days(r) is not None and days(r) < 0))
        q = {"source": s, "open": n, "fresh_7d": pct(sum(1 for r in rs if r.get("new"))),
             "deadline": pct(sum(1 for r in rs if r.get("deadline"))), "value": pct(sum(1 for r in rs if r.get("est_value_usd"))),
             "buyer": pct(sum(1 for r in rs if r.get("buyer"))), "title_en": pct(sum(1 for r in rs if r.get("title_en"))),
             "expired": expired, "dup_in": pct(dup), "mirrored": pct(mirrored),
             "goods": pct(sum(1 for r in rs if r.get("decision") in ("Pursue", "Watch")))}
        flags = []
        if q["deadline"] < 50 or q["buyer"] < 50:
            flags.append("thin parse")
        if q["dup_in"] > 15:
            flags.append("duplicates")
        if expired:
            flags.append(f"{expired} expired still listed")
        if n >= 20 and q["fresh_7d"] == 0:
            flags.append("nothing new")
        q["flags"] = "; ".join(flags)
        out.append(q)
    out.sort(key=lambda q: -q["open"])
    with open(LEADS / "source_quality.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ["source"])
        w.writeheader(); w.writerows(out)
    log.info("source quality: %d sources, %d flagged", len(out), sum(1 for q in out if q["flags"]))
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    for q in main():
        print(q)
