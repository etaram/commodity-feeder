"""Live test of the three new layers: grants/calls, Israeli exemption contracts, integrity advisor."""
import functools
import logging
import sys
sys.path.insert(0, ".")
print = functools.partial(print, flush=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
from leads import grants, il_exemptions, integrity, run  # noqa: E402

print("GRANTS", grants.fetch()[1])
import csv  # noqa: E402
g = list(csv.DictReader(open("data/leads/grants.csv", encoding="utf-8")))
for r in g[:6]:
    print("  ", r["source"], "|", r["closes"], "|", r["title"][:80])
print("IL_EXEMPT", il_exemptions.fetch()[1])
import os  # noqa: E402
e = list(csv.DictReader(open("data/leads/il_exempt.csv", encoding="utf-8"))) if os.path.exists("data/leads/il_exempt.csv") else []
for r in e[:6]:
    print("  ", r["renewal_window"], "|", r["office"][:30], "|", r["title"][:50], "|", r["supplier"][:30], "|", r["amount"], "|", r["end"])
run.merge_awards()
p = integrity.profile(run.AWARD_ROWS)
print("INTEGRITY countries", len(p))
for c in ["ISR", "DEU", "GBR", "USA", "KEN", "ETH", "UGA", "NGA", "IND", "BRA", "UKR", "GTM", "AZE", "ARE", "SAU"]:
    x = p.get(c)
    if x:
        print("  ", c, x["integrity_score"], x["flag"], "| CC", x["control_of_corruption"], "| single-bid", x["single_bid_share"], "| foreign", x["foreign_win_rate"], "|", x["basis"])
