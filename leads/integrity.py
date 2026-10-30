"""Regulation and integrity advisor: can this tender be won on the merits, or is the market closed in practice?

Two independent sources, no guesswork:
  1. Official governance data - World Bank Worldwide Governance Indicators (free API): control of corruption,
     rule of law, regulatory quality, government effectiveness. Range -2.5 (weak) to +2.5 (strong).
  2. What the award records actually show for that country: how many firms bid, how often a single bidder wins,
     and how often a foreign firm wins. A market where one bidder wins nearly everything is closed in practice
     whatever its score says.

Output: data/leads/governance.csv (one row per country) and three fields on every tender - integrity_score (0-100),
integrity_flag (open / caution / high risk) and integrity_note (what it means and what to do).

The advisor is a compliance tool. Pre-tender market dialogue with a buying body is lawful and normal in public
procurement; payments or favours to officials are criminal (Israeli Penal Law 291A, US FCPA, UK Bribery Act) and the
advisor never treats them as an option - a market that needs them is a market to decline.
"""
import csv
import json
import datetime as dt
from collections import defaultdict
from statistics import median

from .common import LEADS, log, session, today

CACHE = LEADS / "cache" / "governance.json"
IND = {"GOV_WGI_CC.EST": "control_of_corruption", "GOV_WGI_RL.EST": "rule_of_law", "GOV_WGI_RQ.EST": "regulatory_quality",
       "GOV_WGI_GE.EST": "government_effectiveness"}
API = "https://api.worldbank.org/v2/country/all/indicator/{}"


def wgi():
    """{iso3: {indicator: value, 'year': y}} from the World Bank API, cached for 30 days."""
    c = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if c.get("date", "") >= str(today() - dt.timedelta(days=30)) and c.get("data"):
        return c["data"]
    s, data = session(), defaultdict(dict)
    for code, name in IND.items():
        try:
            r = s.get(API.format(code), params={"format": "json", "per_page": 20000, "source": 3,
                                                 "date": f"{today().year - 6}:{today().year}"}, timeout=90)
            j = r.json()
            rows = j[1] if isinstance(j, list) and len(j) > 1 and j[1] else []
        except Exception as e:  # noqa: BLE001 - keep the cached copy if the API is down
            log.warning("WGI %s: %s", code, str(e)[:160]); rows = []
        for x in rows:  # newest year with a value per country
            iso = (x.get("countryiso3code") or "").upper()
            if len(iso) != 3 or x.get("value") is None:
                continue
            if data[iso].get(name + "_year", "") < str(x.get("date", "")):
                data[iso][name] = round(float(x["value"]), 3)
                data[iso][name + "_year"] = str(x.get("date", ""))
                data[iso]["year"] = max(data[iso].get("year", ""), str(x.get("date", "")))
        log.info("WGI %s: %d countries", code, len(rows))
    if not data:
        return c.get("data") or {}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"date": str(today()), "data": data}, ensure_ascii=False))
    return data


def market_stats(awards):
    """Per country, from the award records: how many firms bid, how often one bidder wins, how often a foreigner wins."""
    out = defaultdict(lambda: {"n": 0, "bids": [], "single": 0, "with_bids": 0, "foreign": 0, "with_country": 0})
    for a in awards:
        c = (a.get("country") or "").upper()
        if len(c) != 3:
            continue
        x = out[c]; x["n"] += 1
        b = a.get("bids")
        if isinstance(b, int) and 0 < b < 200:
            x["bids"].append(b); x["with_bids"] += 1
            if b == 1:
                x["single"] += 1
        wc = (a.get("winner_country") or "").upper()
        if len(wc) == 3:
            x["with_country"] += 1
            if wc != c:
                x["foreign"] += 1
    return out


def _score(g, m):
    """0-100. Half from official governance, half from the competition actually observed in the awards."""
    gov = None
    if g:
        vals = [g[k] for k in ("control_of_corruption", "rule_of_law") if k in g]
        if vals:
            gov = max(0, min(100, (sum(vals) / len(vals) + 2.5) / 5 * 100))
    obs = None
    if m and m["with_bids"] >= 20:
        single = m["single"] / m["with_bids"]
        med = median(m["bids"])
        obs = max(0, min(100, 100 - single * 70 + min(20, (med - 1) * 10)))
        if m["with_country"] >= 20:
            obs = min(100, obs + min(15, m["foreign"] / m["with_country"] * 30))
    if gov is None and obs is None:
        return None, "no data"
    if gov is None:
        return round(obs), "award records only"
    if obs is None:
        return round(gov), "governance data only"
    return round(gov * 0.5 + obs * 0.5), "governance + award records"


OPEN_NOTE = ("Normal commercial process: prepare the bid on the merits. Pre-tender questions to the buying body, and "
             "market consultation where the rules allow it, are lawful - keep everything in writing.")
CAUTION_NOTE = ("Workable but verify before spending: read the eligibility and local-content rules, check who won the "
                "last comparable contracts, confirm payment terms and currency. Use local counsel for the contract. "
                "Early written contact with the procurement office is lawful and useful.")
RISK_NOTE = ("Few firms bid here and awards repeat to the same suppliers, so a cold bid rarely wins on price alone. "
             "Treat it as a market-entry decision, not a tender: vet a local partner or distributor (written agreement, "
             "no success fees to anyone with influence over the award), run anti-bribery due diligence, and put "
             "compliance terms in every agreement. If winning appears to require payments or favours to officials, "
             "decline the tender - that is criminal under Israeli Penal Law 291A, the US FCPA and the UK Bribery Act.")


def profile(awards):
    """{iso3: row} with the score, flag and advice for every country we have data on."""
    g_all, m_all = wgi(), market_stats(awards)
    out = {}
    for c in set(g_all) | set(m_all):
        g, m = g_all.get(c, {}), m_all.get(c)
        score, basis = _score(g, m)
        if score is None:
            continue
        flag = "open" if score >= 60 else "caution" if score >= 40 else "high risk"
        single = round(m["single"] / m["with_bids"], 3) if m and m["with_bids"] >= 20 else ""
        foreign = round(m["foreign"] / m["with_country"], 3) if m and m["with_country"] >= 20 else ""
        out[c] = {
            "country": c, "integrity_score": score, "flag": flag, "basis": basis,
            "control_of_corruption": g.get("control_of_corruption", ""), "rule_of_law": g.get("rule_of_law", ""),
            "regulatory_quality": g.get("regulatory_quality", ""), "government_effectiveness": g.get("government_effectiveness", ""),
            "wgi_year": g.get("year", ""), "awards_seen": m["n"] if m else 0,
            "median_bidders": median(m["bids"]) if m and m["bids"] else "", "single_bid_share": single,
            "foreign_win_rate": foreign,
            "advice": OPEN_NOTE if flag == "open" else CAUTION_NOTE if flag == "caution" else RISK_NOTE,
        }
    return out


def apply(tenders, awards):
    """Writes governance.csv and sets integrity_score / integrity_flag / integrity_note on every tender."""
    prof = profile(awards)
    if prof:
        rows = sorted(prof.values(), key=lambda r: -r["integrity_score"])
        with open(LEADS / "governance.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    n = defaultdict(int)
    for t in tenders:
        p = prof.get((t.get("country") or "").upper())
        if not p:
            t["integrity_score"] = ""; t["integrity_flag"] = ""; t["integrity_note"] = ""
            n["no data"] += 1
            continue
        note, flag = [], p["flag"]
        if p["single_bid_share"] != "" and p["single_bid_share"] >= 0.5:
            note.append(f"{p['single_bid_share']:.0%} of awards here go to a single bidder")
        if p["foreign_win_rate"] != "":
            note.append(f"foreign firms win {p['foreign_win_rate']:.0%}")
        if t.get("incumbent"):
            note.append("an incumbent supplier already holds this scope")
        days = t.get("days_left")
        if isinstance(days, int) and 0 <= days < 14 and t.get("stage") != "planned":
            note.append(f"only {days} days to prepare, which favours a supplier that knew in advance")
            if flag == "caution":
                flag = "high risk"
        t["integrity_score"] = p["integrity_score"]
        t["integrity_flag"] = flag
        t["integrity_note"] = ("; ".join(note) + ". " if note else "") + p["advice"]
        n[flag] += 1
    log.info("integrity: %d countries profiled, tenders %s", len(prof), dict(n))
    return prof


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    p = profile([])
    for r in sorted(p.values(), key=lambda r: -r["integrity_score"])[:10]:
        print(r["country"], r["integrity_score"], r["flag"], r["basis"])
    print("countries:", len(p))
