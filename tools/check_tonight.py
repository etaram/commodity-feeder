"""Live check of the new layers on current data (no writes to the data files): sanctions screen and GDELT press."""
import csv
import glob
import logging
import sys
import time

sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
from leads import news  # noqa: E402
from leads.common import session  # noqa: E402
from leads.sanctions import load_lists, screen  # noqa: E402

rows = []
for f in sorted(glob.glob("data/leads/sheet/tenders_[0-9][0-9].csv")):
    rows += list(csv.DictReader(open(f, encoding="utf-8")))
before = {r["id"]: r["decision"] for r in rows}
lists = load_lists()
print("LISTS", {k: len(v) for k, v in lists.items() if isinstance(v, list)})
st = screen(rows)
print("SCREEN", st)
changed = [r for r in rows if before[r["id"]] != r["decision"]]
print("DECISIONS CHANGED", len(changed))
for r in rows:
    if r["why"].startswith(("SANCTIONS", "BLOCKED", "RESTRICTED")) and before[r["id"]] in ("Pursue", "Watch"):
        print("  ", r["country"], before[r["id"]], "->", r["decision"], "|", r["buyer"][:50], "|", r["why"][:110])

s = session()
dc = list(csv.DictReader(open("data/leads/deal_calc.csv", encoding="utf-8")))
qs = [q for q in dict.fromkeys(news._query(r["buyer"]) for r in dc if r["decision"] == "Pursue") if q][:12]
ok = found = 0
for q in qs:
    arts = news._fetch(s, q)
    if arts is not None:
        ok += 1; found += bool(arts)
    print("GDELT", q[:50], "->", "error" if arts is None else len(arts))
    time.sleep(5.5)
print("GDELT SUMMARY", {"queries": len(qs), "answered": ok, "with_articles": found})
