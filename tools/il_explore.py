"""Exploration: candidate official lists of Israeli public bodies (data.gov.il CKAN) and Wikidata counts."""
import json, requests
from pathlib import Path
OUT = Path("data/probe/il_explore.txt"); OUT.parent.mkdir(parents=True, exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 SinderResearch"
lines = []
def ck(q):
    r = s.get("https://data.gov.il/api/3/action/package_search", params={"q": q, "rows": 12}, timeout=60).json()
    lines.append(f"### {q}: {r['result']['count']}")
    for p in r["result"]["results"]:
        res = [(x.get("id"), x.get("name"), x.get("format"), x.get("datastore_active")) for x in p.get("resources", [])][:4]
        lines.append(f"- {p['name']} | {p['title']} | {p['organization']['title'] if p.get('organization') else ''} | {res}")
for q in ["רשויות מקומיות", "רשימת רשויות", "מועצות אזוריות", "חברות ממשלתיות", "תאגידי מים וביוב", "חברות עירוניות",
          "תאגידים סטטוטוריים", "בתי חולים", "מוסדות להשכלה גבוהה", "רשויות ניקוז", "מועצות דתיות", "אשכולות", "ישובים"]:
    try: ck(q)
    except Exception as e: lines.append(f"ERR {q} {e}")
SPARQL = """SELECT ?type ?typeLabel (COUNT(DISTINCT ?o) AS ?n) (SUM(IF(BOUND(?w),1,0)) AS ?nw) WHERE {
  ?o wdt:P17 wd:Q801; wdt:P31 ?type. OPTIONAL { ?o wdt:P856 ?w }
  ?type wdt:P279* wd:Q43229.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } } GROUP BY ?type ?typeLabel ORDER BY DESC(?n) LIMIT 120"""
try:
    r = s.get("https://query.wikidata.org/sparql", params={"query": SPARQL, "format": "json"}, timeout=120).json()
    lines.append("### wikidata org types in Israel")
    for b in r["results"]["bindings"]:
        lines.append(f"{b['type']['value'].split('/')[-1]} {b['typeLabel']['value']} n={b['n']['value']} web={b['nw']['value']}")
except Exception as e: lines.append(f"ERR wikidata {e}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines)[:3000])
