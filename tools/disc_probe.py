import sys, os, re, json; sys.path.insert(0, os.getcwd())
import requests
H = {"User-Agent": "Mozilla/5.0"}
def g(u, n=900, **k):
    try:
        r = requests.get(u, headers=H, timeout=45, verify=False, **k)
        print(f"## {u} -> {r.status_code} {r.headers.get('content-type','')[:40]} len={len(r.text)}\n{r.text[:n]}\n", flush=True); return r
    except Exception as e:
        print(f"## {u} ERR {type(e).__name__} {str(e)[:100]}\n", flush=True)
requests.packages.urllib3.disable_warnings()
r = g("https://public.mtender.gov.md/tenders/?offset=2026-10-20T00:00:00.000Z", 600)
try:
    d = r.json(); print("MD keys", list(d.keys()), "n", len(d.get("data", [])), "next", d.get("offset"))
    oc = d["data"][0]["ocid"]; g(f"https://public.mtender.gov.md/tenders/{oc}", 1500)
except Exception as e: print("MD parse", e)
g("https://www.comprasestatales.gub.uy/ocds/rss/2026/10", 700)
g("https://www.comprasestatales.gub.uy/ocds/rss", 400)
r = g("https://tenderboard.gov.bh/Tenders/Tenders", 200)
if r is not None:
    t = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S))
    i = t.find("Tender"); print("BH TEXT", t[2000:3600])
    print("BH links", re.findall(r'href="([^"]*[Tt]ender[^"]*)"', r.text)[:15])
g("https://myprocurement.treasury.gov.my/", 100)
