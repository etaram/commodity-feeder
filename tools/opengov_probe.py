import requests, json, datetime as dt
H = {"User-Agent": "Mozilla/5.0"}
def g(u, **p):
    try:
        r = requests.get(u, params=p, headers=H, timeout=40)
        return r
    except Exception as e:
        print(f"  ERR {u} {type(e).__name__} {str(e)[:100]}"); return None
CKAN = {"mexico": "https://datos.gob.mx", "peru": "https://www.datosabiertos.gob.pe", "argentina": "https://datos.gob.ar",
        "indonesia": "https://data.go.id", "colombia": "https://www.datos.gov.co", "norway": "https://data.norge.no",
        "tenders_guru_pl": None}
for c, base in CKAN.items():
    if not base: continue
    print(f"## {c} {base}")
    for q in ["licitaciones", "contrataciones", "tender", "procurement", "lelang", "anbud"]:
        r = g(base + "/api/3/action/package_search", q=q, rows=6, sort="metadata_modified desc")
        if r is None: break
        if r.status_code != 200:
            print(f"  {q}: HTTP {r.status_code}"); continue
        try:
            res = r.json()["result"]
        except Exception:
            print(f"  {q}: not json"); continue
        print(f"  {q}: count={res['count']}")
        for d in res["results"][:4]:
            print(f"    - {d['name'][:50]} | mod {d['metadata_modified'][:10]} | {sorted({(x.get('format') or '').upper() for x in d.get('resources', [])})} | {d['title'][:70]}")
print("## taiwan pcc (g0v)")
r = g("https://pcc.g0v.ronny.tw/api/listbydate", date=(dt.date.today()-dt.timedelta(days=2)).strftime("%Y%m%d"))
if r is not None: print(" ", r.status_code, r.text[:400].replace("\n", " "))
print("## singapore data.gov.sg")
r = g("https://api-production.data.gov.sg/v2/public/api/datasets", page=1)
if r is not None: print(" ", r.status_code, r.text[:200])
r = g("https://data.gov.sg/api/action/package_search", q="procurement")
if r is not None: print(" ", r.status_code, r.text[:400].replace("\n", " "))
print("## tenders.guru")
for cc in ["pl", "hu", "ro"]:
    r = g(f"https://tenders.guru/{cc}/api/tenders", page=1)
    if r is not None: print(" ", cc, r.status_code, r.text[:300].replace("\n", " "))
print("## mexico comprasmx / peru seace / argentina contrataciones")
for u in ["https://comprasmx.buengobierno.gob.mx/", "https://contratacionesabiertas.osce.gob.pe/", "https://contrataciones.gob.ar/", "https://www.doffin.no/"]:
    r = g(u); print(" ", u, r.status_code if r is not None else "-")
