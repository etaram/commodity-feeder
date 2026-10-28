"""Producers and traders of specific commodities (sulphur, urea, steel, tuna ...) from Wikidata, by product.
Public-tender winners rarely include upstream producers (refineries, gas plants, miners, fishing groups), so this
layer adds them: companies whose Wikidata entry states the product they make (P1056) or an industry that names the
commodity. Cached in data/leads/companies/products.json and refreshed weekly."""
import json
import time

import requests

from .common import LEADS, log
from .wikidata_companies import UA, _q

OUT = LEADS / "companies" / "products.json"
API = "https://www.wikidata.org/w/api.php"
COMMODITIES = [
    "sulfur", "sulfuric acid", "urea", "ammonia", "ammonium nitrate", "ammonium sulfate", "phosphate rock", "phosphoric acid",
    "potash", "diammonium phosphate", "fertilizer", "methanol", "ethylene", "propylene", "polyethylene", "polypropylene",
    "polyvinyl chloride", "caustic soda", "chlorine", "soda ash", "salt", "carbon black", "petroleum coke", "bitumen",
    "crude oil", "natural gas", "liquefied natural gas", "liquefied petroleum gas", "diesel fuel", "jet fuel", "gasoline",
    "fuel oil", "lubricant", "coal", "coke", "iron ore", "pig iron", "steel", "stainless steel", "scrap metal", "aluminium",
    "alumina", "bauxite", "copper", "copper cathode", "nickel", "zinc", "lead", "tin", "cobalt", "lithium", "manganese",
    "chromium", "titanium dioxide", "tungsten", "molybdenum", "gold", "silver", "platinum", "diamond", "uranium",
    "cement", "clinker", "gypsum", "lime", "limestone", "sand", "gravel", "crushed stone", "glass", "ceramic tile",
    "wheat", "maize", "rice", "barley", "soybean", "soybean meal", "sugar", "ethanol", "coffee", "cocoa", "tea",
    "palm oil", "sunflower oil", "rapeseed oil", "olive oil", "cashew", "sesame", "tuna", "canned tuna", "shrimp",
    "salmon", "fish meal", "beef", "pork", "chicken meat", "milk powder", "cheese", "flour", "pasta", "animal feed",
    "cotton", "wool", "natural rubber", "tyre", "timber", "plywood", "wood pellet", "pulp", "paper", "cardboard",
    "pharmaceutical drug", "vaccine", "medical device", "electric cable", "transformer", "solar panel", "battery",
]


def _qid(s, label):
    try:
        r = s.get(API, params={"action": "wbsearchentities", "search": label, "language": "en", "type": "item",
                               "limit": 1, "format": "json"}, timeout=30)
        hit = (r.json().get("search") or [None])[0]
        return hit["id"] if hit else None
    except Exception:  # noqa: BLE001
        return None


def fetch():
    if OUT.exists() and time.time() - OUT.stat().st_mtime < 6 * 86400:
        return [], {"note": "fresh"}
    s = requests.Session(); s.headers["User-Agent"] = UA
    qids = {}
    for name in COMMODITIES:
        q = _qid(s, name)
        if q:
            qids[q] = name
        time.sleep(0.3)
    out, t0 = {}, time.time()
    items = list(qids.items())
    for i in range(0, len(items), 12):
        if time.time() - t0 > 900:
            break
        values = " ".join(f"wd:{q}" for q, _ in items[i:i + 12])
        query = f"""SELECT ?c ?cLabel ?p ?iso ?web ?indLabel WHERE {{
          VALUES ?p {{ {values} }}
          ?c wdt:P1056/wdt:P279? ?p.
          FILTER NOT EXISTS {{ ?c wdt:P576 ?end }}
          OPTIONAL {{ ?c wdt:P17 ?cty. ?cty wdt:P298 ?iso. }}
          OPTIONAL {{ ?c wdt:P856 ?web }} OPTIONAL {{ ?c wdt:P452 ?ind }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,es,pt,de". }} }} LIMIT 20000"""
        rows = _q(s, query)
        for b in rows or []:
            qid = b["c"]["value"].rsplit("/", 1)[-1]
            name = b.get("cLabel", {}).get("value", "")
            if not name or name == qid:
                continue
            x = out.setdefault(qid, {"name": name, "country": b.get("iso", {}).get("value", ""), "website": "",
                                     "products": [], "industries": []})
            prod = qids.get(b["p"]["value"].rsplit("/", 1)[-1])
            if prod and prod not in x["products"]:
                x["products"].append(prod)
            x["website"] = x["website"] or b.get("web", {}).get("value", "")
            ind = b.get("indLabel", {}).get("value", "")
            if ind and ind not in x["industries"] and len(x["industries"]) < 4:
                x["industries"].append(ind)
        time.sleep(2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"commodities": len(qids), "companies": list(out.values())}, ensure_ascii=False))
    log.info("commodity producers: %d commodities resolved, %d companies", len(qids), len(out))
    return [], {"commodities": len(qids), "companies": len(out)}
