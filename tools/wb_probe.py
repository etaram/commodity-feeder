import json, requests
API = "https://search.worldbank.org/api/v3/projects"
for params in ({"format": "json", "rows": 2, "status": "Pipeline"},
               {"format": "json", "rows": 2, "projectstatusdisplay_exact": "Pipeline"},
               {"format": "json", "rows": 2, "fl": "id,project_name,countrycode,status,projectstatusdisplay,totalamt,boardapprovaldate,sector1,impagency,url"}):
    r = requests.get(API, params=params, timeout=60)
    print("==", params, r.status_code)
    try:
        j = r.json()
        print("keys:", list(j)[:8], "total:", j.get("total"))
        p = j.get("projects")
        first = (list(p.values())[0] if isinstance(p, dict) else p[0]) if p else None
        print(json.dumps(first, ensure_ascii=False)[:1500])
    except Exception as e:
        print("ERR", e, r.text[:300])
