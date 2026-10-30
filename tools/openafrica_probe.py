import requests, json, collections
B = "https://open.africa/api/3/action/"
H = {"User-Agent": "Mozilla/5.0"}
out = []
def get(a, **p):
    r = requests.get(B + a, params=p, headers=H, timeout=40)
    out.append(f"{a} {p} -> {r.status_code}")
    return r.json()["result"] if r.ok else None
tot = get("package_list")
out.append(f"packages: {len(tot) if tot else None}")
seen = {}
for q in ["tender", "procurement", "contract", "bid", "supplier", "public procurement", "tenders"]:
    res = get("package_search", q=q, rows=40, sort="metadata_modified desc")
    if not res: continue
    out.append(f"## {q}: count={res['count']}")
    for d in res["results"]:
        if d["id"] in seen: continue
        seen[d["id"]] = 1
        fm = sorted({(x.get('format') or '').upper() for x in d.get("resources", [])})
        out.append(f"- {d['name']} | {d.get('organization',{}).get('title') if d.get('organization') else ''} | mod {d['metadata_modified'][:10]} | res {len(d.get('resources',[]))} {fm} | {d['title'][:80]}")
print("\n".join(out))
