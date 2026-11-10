"""Ethiopian coffee from the Ethiopian Export Market site (ethiopianexportmarket.com; robots.txt allows every page).

The site republishes the Ethiopian Coffee and Tea Authority's export record and hosts a marketplace of exporter lots.
The official Ethiopian sites themselves do not answer from outside the country, so this is the reachable copy. Read:

  exporters   the ranking of coffee exporters for the Ethiopian year shown (name, export value, tonnes): companies with a
              recorded export volume, and each one's average export price (value / tonnes)
  buyers      the same ranking for foreign buyers
  lots        marketplace offers: origin, grade, process, USD per tonne, quantity, minimum order, incoterm, seller.
              A listing is the seller's own claim; the lots carry the age the site shows ("27 days ago")
  roasted     roasted coffee export prices by grade

Outputs: data/leads/eth_exporters.csv and eth_buyers.csv (public ranking), and price rows through leads/origin_prices.py.
"""
import csv
import re
from datetime import date, timedelta

import requests

from .common import LEADS, log

BASE = "https://ethiopianexportmarket.com"
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
EXPORTERS, BUYERS = LEADS / "eth_exporters.csv", LEADS / "eth_buyers.csv"


def _text(path):
    h = requests.get(BASE + path, headers=UA, timeout=45).text
    t = re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))
    t = t.replace("&amp;", "&").replace("&#x27;", "'").replace("&quot;", '"')
    return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", t))


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def _ranking(t, head):
    """Rows of one ranking block: '# | 1 | NAME | $222.06 | M | 44,197.707 | ton'."""
    i = t.find(head)
    if i < 0:
        return "", []
    year = re.search(r"(\d{4}) E\.C", t[i:i + 200])
    block = t[i:]
    nxt = re.search(r"Top coffee (buyers|exporters)", block[len(head):])
    if nxt:
        block = block[:len(head) + nxt.start()]
    rows = []
    for m in re.finditer(r"# \| (\d+) \| ([^|]{2,80}?) \| \$([\d.,]+) \| (M|K|B)? ?\|? ?([\d.,]+) \| ton", block):
        mult = {"M": 1e6, "K": 1e3, "B": 1e9}.get(m.group(4) or "", 1)
        v, tons = _num(m.group(3)), _num(m.group(5))
        if v and tons:
            rows.append({"rank": int(m.group(1)), "name": m.group(2).strip(), "value_usd": round(v * mult), "tons": tons})
    return (year.group(1) if year else ""), rows


def _lots(t):
    """Marketplace cards: 'Supply | Sidamo | Sidamo Grade 1 Unwashed | Grade 1 · Unwashed | $10,600 | per ton | Quantity | 25 t |
    Min order | 19 t | Incoterms | FOB | Rami Coffee Roasters | 27 days ago | · | Addis Ababa'."""
    out = []
    for m in re.finditer(r"Supply \| ([^|]{2,40}) \| ([^|]{4,80}) \| Grade (\w+) · (\w+) \| \$([\d,.]+) \| per ton \| Quantity \| ([\d,.]+) t \| Min order \| ([\d,.]+) t \| "
                         r"Incoterms \| ([^|]{2,30}) \| ([^|]{2,80}) \| (\d+) (day|days|hour|hours|month|months) ago", t):
        age = int(m.group(10)) * {"day": 1, "days": 1, "hour": 0, "hours": 0, "month": 30, "months": 30}[m.group(11)]
        price = _num(m.group(5))
        if price and 1000 < price < 60000:
            out.append({"origin_area": m.group(1).strip(), "lot": m.group(2).strip(), "grade": m.group(3), "process": m.group(4), "usd_t": price, "qty_t": _num(m.group(6)),
                        "min_t": _num(m.group(7)), "incoterm": m.group(8).strip(), "seller": m.group(9).strip(), "date": (date.today() - timedelta(days=age)).isoformat()})
    return out


def _roasted(t):
    i = t.find("Roasted coffee prices")
    if i < 0:
        return "", []
    age = re.search(r"\| (\d+) days? ago", t[i:i + 120])
    d = (date.today() - timedelta(days=int(age.group(1)) if age else 0)).isoformat()
    return d, [(m.group(1), _num(m.group(2))) for m in re.finditer(r"Grade \| (\d) \| [\d.]+ \| USc/lb \| \$ \| ([\d,.]+) \| per ton", t[i:i + 1500])]


def _name(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = s.title() if s.isupper() else s
    return re.sub(r"\bPlc\b", "PLC", re.sub(r"\bP\.L\.C\b", "P.L.C", s, flags=re.I))


def fetch():
    insight, market = _text("/insight"), _text("/marketplace")
    year, exporters = _ranking(insight, "Top coffee exporters")
    _, buyers = _ranking(insight, "Top coffee buyers")
    lots = _lots(market)
    rdate, roasted = _roasted(insight)
    by_seller = {}
    for lot in lots:
        by_seller.setdefault(lot["seller"], []).append(lot)
    LEADS.mkdir(parents=True, exist_ok=True)
    src = "Ethiopian Coffee and Tea Authority export record, as published by Ethiopian Export Market"
    if exporters:   # an empty read never replaces the last good file
        with open(EXPORTERS, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["supplier", "country", "kind", "rank", "year_ec", "value_usd", "tons", "avg_usd_kg", "offers", "source", "source_url", "fetched"])
            w.writeheader()
            for e in exporters:
                w.writerow({"supplier": _name(e["name"]), "country": "ETH", "kind": "export record", "rank": e["rank"], "year_ec": year, "value_usd": e["value_usd"], "tons": e["tons"],
                            "avg_usd_kg": round(e["value_usd"] / (e["tons"] * 1000), 3), "offers": "", "source": src, "source_url": BASE + "/insight", "fetched": date.today().isoformat()})
            known = {_name(e["name"]).lower() for e in exporters}
            for seller, ls in by_seller.items():   # marketplace sellers that are not in the ranking: a listing, the seller's own claim
                if seller.lower() in known:
                    continue
                w.writerow({"supplier": seller, "country": "ETH", "kind": "marketplace listing", "rank": "", "year_ec": "", "value_usd": "", "tons": "", "avg_usd_kg": "",
                            "offers": "; ".join(f"{x['lot']} {x['incoterm'].split(' ')[0]} ${x['usd_t']:,.0f}/t ({x['qty_t']:g} t)" for x in ls[:4]),
                            "source": "Ethiopian Export Market marketplace (seller's own listing)", "source_url": BASE + "/marketplace", "fetched": date.today().isoformat()})
    if buyers:
        with open(BUYERS, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["buyer", "rank", "year_ec", "value_usd", "tons", "avg_usd_kg", "source", "source_url", "fetched"])
            w.writeheader()
            for b in buyers:
                w.writerow({"buyer": _name(b["name"]), "rank": b["rank"], "year_ec": year, "value_usd": b["value_usd"], "tons": b["tons"],
                            "avg_usd_kg": round(b["value_usd"] / (b["tons"] * 1000), 3), "source": src, "source_url": BASE + "/insight", "fetched": date.today().isoformat()})
    log.info("eth market: %d exporters, %d buyers (%s E.C.), %d lots from %d sellers, %d roasted grades", len(exporters), len(buyers), year, len(lots), len(by_seller), len(roasted))
    return {"year": year, "exporters": exporters, "buyers": buyers, "lots": lots, "roasted": roasted, "roasted_date": rdate}
