"""Plays: deal theses the engine writes from signals, not from a single tender (see dealdesk/BRAIN.md).

Each play: kind, country, sector, title, thesis (one line, from the numbers), role Sinder would take, evidence
(source links), value_usd where a source states one (else blank), confidence, next_step, and the entity it is
about (buyer or winner), so the panel can open it. Nothing here is sent to anyone; a play is a starting point.
Run inside leads.run after the tender brain: python -m leads.plays  ->  data/leads/plays.csv
"""
import csv
import datetime as dt
import re

from .common import LEADS, log, today
from .regions import iso3, region
from .dealfit import EMERGING, supplier_table

GOODS_SECTORS = {"Agriculture & food", "Energy, fuels & utilities", "Power & electrical equipment", "Mining, minerals & metals",
                 "Chemicals & plastics", "Textiles, apparel & leather", "Construction materials & building systems",
                 "Water & wastewater", "Industrial & construction machinery", "Vehicles, rolling stock, ships & aircraft",
                 "Defence & security", "Healthcare & pharmaceuticals", "Scientific & measuring instruments", "ICT & telecom",
                 "Furniture, appliances & consumer goods"}
WORKS_SECTORS = {"Building construction works", "Transport & civil infrastructure works", "Water & wastewater"}
LICENSED = re.compile(r"pharma|medicin|drug|vaccin", re.I)


def _rows(name):
    p = LEADS / name
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def _n(v, d=0.0):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return d


def supply_the_winner(sup):
    """A company that wins goods or works contracts again and again needs cheaper inputs. Where the universe holds
    Asian exporters for that sector, the winner is a customer for Sinder's sourcing, not a competitor."""
    out = []
    for r in _rows("competitors.csv"):
        sec, wins, usd = r.get("group") or "", _n(r.get("wins_12m")), _n(r.get("won_usd_est"))
        if wins < 3 or usd < 2_000_000 or sec not in GOODS_SECTORS | WORKS_SECTORS or LICENSED.search(sec):
            continue
        s = sup["sector"].get(sec) or {}
        asia = s.get("asia_exporters", 0)
        if asia < 5:
            continue
        bc = (r.get("buyer_countries") or "").split()
        country = r.get("supplier_country") or (bc[0] if bc else "")
        emerging = any(region(c) in EMERGING for c in bc + [country] if c)
        conf = min(0.9, 0.4 + 0.05 * min(wins, 6) + (0.15 if emerging else 0) + (0.1 if usd > 20_000_000 else 0))
        role = "sub-supplier to the contractor" if sec in WORKS_SECTORS else "sourcing partner (principal or agent)"
        out.append({
            "kind": "supply the winner", "country": country, "sector": sec,
            "title": f"{r['supplier'][:80]}: {int(wins)} wins, ${usd/1e6:,.0f}M in 12 months",
            "thesis": f"Wins {sec.lower()} contracts repeatedly ({', '.join(bc[:4]) or country}); the universe holds {asia} proven Asian exporters in this sector. Offer them as a cheaper input, not a rival bid.",
            "role": role, "entity": r["supplier"], "entity_kind": "winner", "value_usd": "",
            "evidence": "awards: " + str(int(wins)) + " in 12 months; exporters: supplier universe", "confidence": round(conf, 2),
            "next_step": "Open the winner's awards, pick the one input they buy most, and get two Asian quotes before the approach.",
            "emerging": emerging,
        })
    out.sort(key=lambda x: (-x["confidence"], x["title"]))
    return out[:400]


def arbitrage_gaps(sup):
    """A country pays well above the benchmark for an import line, and the universe holds exporters for that heading."""
    out = []
    for r in _rows("markets.csv"):
        prem, imp = r.get("premium_vs_benchmark_pct"), _n(r.get("imports_usd"))
        if prem in ("", None) or _n(prem) < 12 or imp < 20_000_000:
            continue
        # a gap above 150%, or above 60% against a derived benchmark, is a unit or grade mismatch, not a margin
        if _n(prem) > 150 or (r.get("benchmark_source") == "derived" and _n(prem) > 60):
            continue
        hs = (r.get("hs6") or "").replace("HS ", "")[:4]
        s = sup["hs"].get(hs) or {}
        if s.get("suppliers", 0) < 3:
            continue
        c = iso3(r.get("country") or "") or ""
        if not c or len(c) != 3:
            continue
        conf = min(0.85, 0.35 + min(_n(prem), 60) / 150 + (0.1 if s.get("asia_suppliers", 0) >= 3 else 0) + (0.1 if region(c) in EMERGING else 0))
        out.append({
            "kind": "arbitrage gap", "country": c, "sector": r.get("group") or "",
            "title": f"{(r.get('product') or '')[:70]} into {r.get('country')}",
            "thesis": f"Imports ${imp/1e6:,.0f}M a year at {r.get('unit_value_usd_kg')} $/kg, {prem}% above the {r.get('benchmark_source')} benchmark ({r.get('benchmark_usd_kg')} $/kg); {s.get('suppliers')} proven suppliers of HS {hs} in the universe ({s.get('asia_suppliers', 0)} Asian).",
            "role": "principal (buy at benchmark, sell into the gap)", "entity": f"HS {hs}", "entity_kind": "commodity", "value_usd": round(imp),
            "evidence": f"UN Comtrade {r.get('year')}; benchmark {r.get('benchmark_source')}", "confidence": round(conf, 2),
            "next_step": "Find the three largest importers of this line in the country (customs or trade registry), then price a CIF offer from the universe.",
            "emerging": region(c) in EMERGING,
        })
    out.sort(key=lambda x: (-x["confidence"], -_n(x["value_usd"])))
    return out[:300]


def pre_tender(sup):
    """A buyer that awards the same sector on a yearly cycle: approach it 60-90 days before the next expected award."""
    out, t = [], today()
    t = t if isinstance(t, dt.date) else dt.date.fromisoformat(str(t))
    for r in _rows("buyers.csv"):
        sec, nx = r.get("group") or "", r.get("next_expected") or ""
        if sec not in GOODS_SECTORS or LICENSED.search(sec) or not nx:
            continue
        try:
            d = (dt.date.fromisoformat(nx) - t).days
        except ValueError:
            continue
        if not (20 <= d <= 120) or _n(r.get("awards_12m")) < 2:
            continue
        s = sup["sector"].get(sec) or {}
        if s.get("exporters", 0) < 10:
            continue
        c = r.get("country") or ""
        med = _n(r.get("median_award_usd"))
        conf = min(0.85, 0.4 + (0.15 if region(c) in EMERGING else 0) + (0.1 if med > 500_000 else 0) + (0.1 if r.get("buyer_email") else 0))
        out.append({
            "kind": "pre-tender approach", "country": c, "sector": sec,
            "title": f"{r['buyer'][:80]}: next {sec.lower()} award expected {nx}",
            "thesis": f"{r.get('awards_12m')} awards in 12 months (median ${med/1e6:,.1f}M), months {r.get('award_months')}; current suppliers: {(r.get('current_suppliers') or '-')[:90]}.",
            "role": "direct bid or agent for a proven supplier", "entity": r["buyer"], "entity_kind": "buyer", "value_usd": round(med) if med else "",
            "evidence": r.get("last_notice") or "award history", "confidence": round(conf, 2),
            "next_step": f"Write to the buyer {min(d, 60)} days before the expected notice with a reference list from the universe; register on its portal now.",
            "emerging": region(c) in EMERGING,
        })
    out.sort(key=lambda x: (-x["confidence"], x["title"]))
    return out[:400]


def build():
    sup = supplier_table()
    plays = supply_the_winner(sup) + arbitrage_gaps(sup) + pre_tender(sup)
    cols = ["kind", "country", "region", "sector", "title", "thesis", "role", "entity", "entity_kind", "value_usd",
            "evidence", "confidence", "next_step", "built"]
    for p in plays:
        p["region"] = region(p["country"]) if p["country"] else ""
        p["built"] = str(today())
    # Sinder's edge is in emerging markets: they lead, and no single kind or region floods the list
    plays.sort(key=lambda p: (not p.get("emerging"), -p["confidence"]))
    kept, seen = [], {}
    for p in plays:
        k = (p["kind"], p.get("emerging", False))
        if seen.get(k, 0) >= (150 if p.get("emerging") else 60):
            continue
        seen[k] = seen.get(k, 0) + 1
        kept.append(p)
    plays = kept
    with open(LEADS / "plays.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows([{k: v for k, v in p.items() if k != "emerging"} for p in plays])
    log.info("plays: %d (%s)", len(plays), ", ".join(f"{k}={sum(1 for p in plays if p['kind'] == k)}" for k in ("supply the winner", "arbitrage gap", "pre-tender approach")))
    return plays


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    for p in build()[:8]:
        print(p["confidence"], p["kind"], p["country"], "|", p["title"][:70], "|", p["thesis"][:100])
