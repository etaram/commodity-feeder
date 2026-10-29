"""Exploration 2: sample rows of candidate official lists (data.gov.il datastore) + Wikidata check."""
import json, requests
from pathlib import Path
OUT = Path("data/probe/il_explore2.txt")
s = requests.Session(); s.headers["User-Agent"] = "SinderProcurementResearch/1.0 (https://github.com/etaram/commodity-feeder)"
L = []
def pkg(name):
    r = s.get("https://data.gov.il/api/3/action/package_show", params={"id": name}, timeout=60).json()["result"]
    return r
def sample(rid, n=4, q=None):
    p = {"resource_id": rid, "limit": n}
    if q: p["q"] = q
    r = s.get("https://data.gov.il/api/3/action/datastore_search", params=p, timeout=60).json()["result"]
    L.append(f"  total={r.get('total')} fields={[f['id'] for f in r['fields']]}")
    for x in r["records"]:
        L.append("  " + json.dumps(x, ensure_ascii=False)[:700])
# chovot pirsum datasets
r = s.get("https://data.gov.il/api/3/action/package_search", params={"q": "chovotpirsum", "rows": 30}, timeout=60).json()
names = [p["name"] for p in r["result"]["results"]]
r2 = s.get("https://data.gov.il/api/3/action/package_search", params={"q": "חובות הפרסום", "rows": 30}, timeout=60).json()
names += [p["name"] for p in r2["result"]["results"] if p["name"] not in names]
for n in ["municipal-authorities", "gsa", "councils"] + names:
    try:
        p = pkg(n); L.append(f"### {n} | {p['title']}")
        for res in p["resources"][:3]:
            L.append(f" res {res['id']} {res['name']} {res.get('format')} ds={res.get('datastore_active')}")
            if res.get("datastore_active"):
                try: sample(res["id"])
                except Exception as e: L.append(f"  ERR {e}")
    except Exception as e:
        L.append(f"ERR {n} {e}")
Q = """SELECT ?o ?oLabel ?w ?typeLabel WHERE { ?o wdt:P17 wd:Q801; wdt:P856 ?w; wdt:P31 ?type.
 VALUES ?type { wd:Q4830453 wd:Q270791 wd:Q2659904 wd:Q7210356 wd:Q16917 wd:Q3918 wd:Q31855 wd:Q1110794 wd:Q15911314 wd:Q891723 wd:Q6881511 wd:Q18127 wd:Q1520223 wd:Q2096489 wd:Q515 wd:Q1093829 wd:Q44782 wd:Q190928 wd:Q15275719}
 SERVICE wikibase:label { bd:serviceParam wikibase:language "he,en". } }"""
try:
    r = s.get("https://query.wikidata.org/sparql", params={"query": Q, "format": "json"}, timeout=180)
    b = r.json()["results"]["bindings"]
    from collections import Counter
    L.append(f"### wikidata with website: {len(b)}")
    L.append(str(Counter(x['typeLabel']['value'] for x in b).most_common(30)))
    for x in b[:15]: L.append(f"  {x['oLabel']['value']} | {x['typeLabel']['value']} | {x['w']['value']}")
except Exception as e: L.append(f"ERR wikidata {e} {r.status_code if 'r' in dir() else ''} {r.text[:200] if 'r' in dir() else ''}")
OUT.write_text("\n".join(L), encoding="utf-8")
