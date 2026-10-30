import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "curl_cffi"], check=False)
from curl_cffi import requests as cr
for ipp in (10, 100):
    u = f"https://myprocurement.treasury.gov.my/procurements/fetch?type=advertisements&category=tender&itemsPerPage={ipp}&page=2"
    r = cr.get(u, impersonate="chrome", timeout=60, headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/html"})
    print("###", ipp, r.status_code, r.headers.get("content-type"), len(r.text), flush=True)
    print(r.text[:1200].replace("\n", " "), flush=True)
