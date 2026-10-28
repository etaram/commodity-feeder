"""Notable producers and traders by country from Wikidata (companies with a stated industry; website when known).
Tier B in the Supplier Universe (established, notable companies) next to tier A (proven public-tender winners).
Cached per country in data/leads/companies/wikidata/<ISO3>.json; ~25 countries refreshed per run (90-day cycle)."""
import datetime as dt
import json
import re
import time

import requests

from .common import LEADS, log, today
from .sectors import classify

URL = "https://query.wikidata.org/sparql"
UA = "SinderOpportunityEngine/1.0 (https://github.com/etaram/commodity-feeder; procurement research)"
DIR = LEADS / "companies" / "wikidata"
KEEP = {"AGRI_FOOD", "ENERGY", "POWER", "MINING_METALS", "CHEMICALS", "TEXTILES", "CONSTR_MAT", "MACHINERY",
        "TRANSPORT_EQ", "DEFENCE", "HEALTH", "LAB", "ICT", "CONSUMER", "WATER", "LOGISTICS", "BUILDING", "INFRA",
        "ENGINEERING"}
TRADE = re.compile(r"trad|wholesale|commodit|import|export|distribut|merchant", re.I)
PRIORITY = ("NGA ETH EGY ZAF KEN TZA UGA GHA CIV SEN CMR MAR DZA TUN AGO MOZ ZMB ZWE COD SDN BRA ARG CHL PER COL ECU "
            "MEX URY PRY BOL VEN IND PAK BGD VNM THA IDN MYS PHL CHN TUR SAU ARE QAT KWT OMN JOR ISR IRN KAZ UZB UKR "
            "POL ROU CZE ITA ESP FRA DEU NLD BEL GBR NOR SWE FIN DNK PRT GRC AUT CHE HUN SRB HRV BGR SVK SVN LTU LVA "
            "EST IRL USA CAN AUS NZL JPN KOR TWN SGP LKA NPL MMR KHM").split()


def _q(s, query):
    for attempt in range(3):
        try:
            r = s.get(URL, params={"query": query, "format": "json"}, timeout=120)
            if r.status_code == 429:
                time.sleep(30); continue
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            log.warning("wikidata %s", r.status_code)
        except Exception as e:  # noqa: BLE001
            log.warning("wikidata: %s", e)
        time.sleep(10)
    return None


def _country_qids(s):
    p = DIR / "_countries.json"
    if p.exists():
        return json.loads(p.read_text())
    rows = _q(s, "SELECT ?c ?iso WHERE { ?c wdt:P298 ?iso. ?c wdt:P31 wd:Q6256. }") or []
    m = {b["iso"]["value"]: b["c"]["value"].rsplit("/", 1)[-1] for b in rows}
    DIR.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(m))
    return m


def _country(s, qid):
    q = f"""SELECT ?c ?cLabel ?indLabel ?web ?emp WHERE {{
      VALUES ?t {{ wd:Q4830453 wd:Q783794 wd:Q6881511 wd:Q891723 wd:Q1589009 wd:Q22687 }}
      ?c wdt:P31 ?t; wdt:P17 wd:{qid}; wdt:P452 ?ind.
      FILTER NOT EXISTS {{ ?c wdt:P576 ?dissolved }}
      OPTIONAL {{ ?c wdt:P856 ?web }} OPTIONAL {{ ?c wdt:P1128 ?emp }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,es,pt,de". }} }} LIMIT 30000"""
    rows = _q(s, q)
    if rows is None:
        return None
    out = {}
    for b in rows:
        qid_c = b["c"]["value"].rsplit("/", 1)[-1]
        name = b.get("cLabel", {}).get("value", "")
        if re.fullmatch(r"Q\d+", name):
            continue
        x = out.setdefault(qid_c, {"qid": qid_c, "name": name, "industries": set(), "website": "", "employees": ""})
        x["industries"].add(b.get("indLabel", {}).get("value", ""))
        x["website"] = x["website"] or b.get("web", {}).get("value", "")
        x["employees"] = x["employees"] or b.get("emp", {}).get("value", "")
    prods = {}
    pq = f"""SELECT ?c ?pLabel WHERE {{ ?c wdt:P17 wd:{qid}; wdt:P452 ?ind; wdt:P1056 ?p.
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,es,pt,de". }} }} LIMIT 40000"""
    for b in _q(s, pq) or []:
        lab = b.get("pLabel", {}).get("value", "")
        if lab and not re.fullmatch(r"Q\d+", lab):
            prods.setdefault(b["c"]["value"].rsplit("/", 1)[-1], []).append(lab)
    res = []
    for x in out.values():
        inds = "; ".join(sorted(i for i in x["industries"] if i and not re.fullmatch(r"Q\d+", i)))
        sec, _ = classify(inds)
        trader = bool(TRADE.search(inds))
        if sec not in KEEP and not trader:
            continue
        res.append({"qid": x["qid"], "name": x["name"], "industries": inds[:200], "sector": sec,
                    "trader": trader, "website": x["website"], "employees": x["employees"],
                    "products": "; ".join(dict.fromkeys(prods.get(x["qid"], [])))[:200]})
    return res


def fetch():
    s = requests.Session(); s.headers["User-Agent"] = UA
    DIR.mkdir(parents=True, exist_ok=True)
    qids = _country_qids(s)
    t = today(); cut = str(t - dt.timedelta(days=90))
    order = PRIORITY + sorted(c for c in qids if c not in PRIORITY)
    done, total, t0 = 0, 0, time.time()
    for iso in order:
        if iso not in qids or time.time() - t0 > 780 or done >= 60:
            continue
        p = DIR / f"{iso}.json"
        if p.exists() and json.loads(p.read_text()).get("v") == 2 and json.loads(p.read_text()).get("updated", "") >= cut:
            continue
        rows = _country(s, qids[iso])
        if rows is None:
            continue
        p.write_text(json.dumps({"v": 2, "updated": str(t), "country": iso, "companies": rows}, ensure_ascii=False))
        done += 1; total += len(rows)
        time.sleep(2)
    have = len(list(DIR.glob("[A-Z][A-Z][A-Z].json")))
    log.info("wikidata companies: %d countries refreshed (%d companies), %d countries cached", done, total, have)
    return [], {"countries": done, "companies": total, "cached": have}
