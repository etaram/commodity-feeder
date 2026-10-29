import json, re, requests
from pathlib import Path
s = requests.Session(); s.headers.update({"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0"})
U = "https://sam.gov/api/prod/sgs/v1/search/"
out = []
for sa in ["SBA", "SBP", "8A", "HZC", "SDVOSBC", "WOSB", "NONE", "xyz"]:
    j = s.get(U, params={"index": "opp", "page": 0, "size": 3, "mode": "search", "is_active": "true", "set_aside": sa}, timeout=60).json()
    out.append(f"set_aside={sa}: {j.get('page',{}).get('totalElements')}")
# detail of several combined notices, print solicitation block and setAside-like keys
j = s.get(U, params={"index": "opp", "page": 0, "size": 12, "mode": "search", "is_active": "true", "notice_type": "k", "sort": "-modifiedDate"}, timeout=60).json()
for o in j["_embedded"]["results"]:
    d = s.get(f"https://sam.gov/api/prod/opps/v2/opportunities/{o['_id']}", timeout=60).json()
    d2 = d.get("data2", {})
    out.append(json.dumps({"title": o["title"][:60], "solicitation": d2.get("solicitation"), "pop": d2.get("placeOfPerformance"),
                           "psc": d2.get("classificationCode"), "naics": d2.get("naics"), "keys": sorted(d2.keys())})[:900])
j = s.get(U, params={"index": "opp", "page": 0, "size": 20, "mode": "search", "is_active": "true", "q": "Israel"}, timeout=60).json()
for o in j["_embedded"]["results"]:
    out.append("ISR: " + o["title"][:100] + " | " + (o.get("type") or {}).get("value", ""))
Path("data/probe/sam_probe.txt").write_text("\n".join(out))
