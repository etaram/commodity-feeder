import json, sys
sys.path.insert(0, ".")
from leads.common import session
s = session()
for fl in ["", "id,project_name,sector1,sector,mjsector1Name,sectorcode,mjsectorcode,theme1,sector1Name"]:
    params = {"format": "json", "rows": 3, "os": 0}
    if fl: params["fl"] = fl
    j = s.get("https://search.worldbank.org/api/v3/projects", params=params, timeout=90).json()
    projs = j.get("projects") or {}
    items = list(projs.values()) if isinstance(projs, dict) else projs
    print("== fl:", fl or "(all)")
    for p in items[:2]:
        print(json.dumps({k: p[k] for k in p if "sect" in k.lower() or k in ("id", "project_name")}, ensure_ascii=False)[:1500])
        if not fl: print("keys:", sorted(p.keys())[:80])
