"""Leading listed companies by country from Wikidata (companies with a stock-exchange listing, ranked by market cap,
then employees). Fills the gap left by award-based and industry-tagged sources: the large, well-known corporations.
Cached per country in data/leads/companies/listed/<ISO3>.json (top 400 per country, 60-day cycle)."""
import datetime as dt
import json
import re
import time

import requests

from .common import LEADS, log, today
from .sectors import classify
from .wikidata_companies import PRIORITY, UA, _country_qids, _q

DIR = LEADS / "companies" / "listed"
TOP = 400
TRADE = re.compile(r"trad|wholesale|commodit|import|export|distribut|merchant", re.I)


def _country(s, qid):
    q = f"""SELECT ?c ?cLabel ?indLabel ?web ?emp ?cap ?exLabel WHERE {{
      ?c wdt:P414 ?ex; wdt:P17 wd:{qid}.
      FILTER NOT EXISTS {{ ?c wdt:P576 ?dissolved }}
      OPTIONAL {{ ?c wdt:P452 ?ind }} OPTIONAL {{ ?c wdt:P856 ?web }} OPTIONAL {{ ?c wdt:P1128 ?emp }}
      OPTIONAL {{ ?c wdt:P2226 ?cap }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,es,pt,de". }} }} LIMIT 40000"""
    rows = _q(s, q)
    if rows is None:
        return None
    out = {}
    for b in rows:
        qc = b["c"]["value"].rsplit("/", 1)[-1]
        name = b.get("cLabel", {}).get("value", "")
        if re.fullmatch(r"Q\d+", name) or len(name) < 3:
            continue
        x = out.setdefault(qc, {"qid": qc, "name": name, "industries": set(), "website": "", "employees": 0,
                                "cap": 0.0, "exchanges": set()})
        ind = b.get("indLabel", {}).get("value", "")
        if ind and not re.fullmatch(r"Q\d+", ind):
            x["industries"].add(ind)
        ex = b.get("exLabel", {}).get("value", "")
        if ex and not re.fullmatch(r"Q\d+", ex):
            x["exchanges"].add(ex)
        x["website"] = x["website"] or b.get("web", {}).get("value", "")
        try:
            x["employees"] = max(x["employees"], int(float(b.get("emp", {}).get("value", 0))))
            x["cap"] = max(x["cap"], float(b.get("cap", {}).get("value", 0)))
        except ValueError:
            pass
    ranked = sorted(out.values(), key=lambda x: (-x["cap"], -x["employees"]))[:TOP]
    res = []
    for x in ranked:
        inds = "; ".join(sorted(x["industries"]))
        sec, _ = classify(inds or x["name"])
        res.append({"qid": x["qid"], "name": x["name"], "industries": inds[:200], "sector": sec,
                    "trader": bool(TRADE.search(inds)), "website": x["website"],
                    "employees": str(x["employees"] or ""), "market_cap_usd": round(x["cap"]) if x["cap"] else "",
                    "listed_on": "; ".join(sorted(x["exchanges"]))[:120], "products": ""})
    return res


def fetch():
    s = requests.Session(); s.headers["User-Agent"] = UA
    DIR.mkdir(parents=True, exist_ok=True)
    qids = _country_qids(s)
    t = today(); cut = str(t - dt.timedelta(days=60))
    order = PRIORITY + sorted(c for c in qids if c not in PRIORITY)
    done, total, t0 = 0, 0, time.time()
    for iso in order:
        if iso not in qids or time.time() - t0 > 780 or done >= 40:
            continue
        p = DIR / f"{iso}.json"
        if p.exists() and json.loads(p.read_text()).get("updated", "") >= cut:
            continue
        rows = _country(s, qids[iso])
        if rows is None:
            continue
        p.write_text(json.dumps({"v": 1, "updated": str(t), "country": iso, "companies": rows}, ensure_ascii=False))
        done += 1; total += len(rows)
        time.sleep(2)
    have = len(list(DIR.glob("[A-Z][A-Z][A-Z].json")))
    log.info("listed companies: %d countries refreshed (%d companies), %d cached", done, total, have)
    return [], {"countries": done, "companies": total, "cached": have}
