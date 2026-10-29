import json, requests
from pathlib import Path
s = requests.Session(); s.headers.update({"Accept": "application/hal+json", "User-Agent": "Mozilla/5.0"})
U = "https://sam.gov/api/prod/sgs/v1/search/"
out = []
r = s.get(U, params={"index": "opp", "page": 0, "size": 5, "sort": "-modifiedDate", "mode": "search", "is_active": "true"}, timeout=60).json()
out.append("TOTAL active: " + json.dumps(r.get("page")))
res = r["_embedded"]["results"]
out.append("KEYS: " + json.dumps(sorted(res[0].keys())))
out.append(json.dumps(res[0], indent=1)[:6000])
for extra in [{"notice_type": "o"}, {"notice_type": "k"}, {"notice_type": "p"}, {"notice_type": "r"},
              {"response_date.from": "2026-11-01-05:00", "response_date.to": "2026-11-08-05:00"},
              {"set_aside": "NONE"}, {"q": "Israel"}]:
    try:
        j = s.get(U, params={"index": "opp", "page": 0, "size": 1, "mode": "search", "is_active": "true", **extra}, timeout=60).json()
        out.append(f"{extra}: {j.get('page')}")
    except Exception as e:
        out.append(f"{extra}: ERR {e}")
# detail endpoint for set-aside / place of performance
oid = res[0]["_id"]
for u in [f"https://sam.gov/api/prod/opps/v2/opportunities/{oid}", f"https://sam.gov/api/prod/opps/v3/opportunities/{oid}"]:
    try:
        d = s.get(u, timeout=60)
        out.append(f"DETAIL {u} {d.status_code} " + d.text[:4000])
    except Exception as e:
        out.append(f"DETAIL ERR {e}")
Path("data/probe/sam_probe.txt").write_text("\n".join(out))
