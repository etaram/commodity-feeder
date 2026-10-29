import re
from pathlib import Path
from curl_cffi import requests as cr
s = cr.Session(impersonate="chrome", timeout=40)
out = []
t = s.get("https://www.txsmartbuy.gov/esbd").text
out.append("TX services: " + str(sorted(set(re.findall(r'[\w/.-]*\.ss[^"\'\s]{0,60}', t)))[:30]))
out.append("TX esbd refs: " + str(sorted(set(re.findall(r'[^"\'\s]*esbd[^"\'\s]{0,80}', t, re.I)))[:30]))
for u in ["https://www.txsmartbuy.gov/app/extensions/CPA/CPAMain/1.0.0/services/ESBD.Service.ss?page=1&status=1",
          "https://www.txsmartbuy.gov/app/extensions/CPA/CPAMain/1.0.0/services/ESBD.Service.ss?c=852252&n=2&page=1"]:
    try:
        r = s.get(u); out.append(f"TRY {u} {r.status_code} {r.text[:600]}")
    except Exception as e:
        out.append(f"TRY {u} ERR {e}")
t = s.get("https://vendor.myfloridamarketplace.com/search/bids").text
out.append("FL: " + t[:1100])
js = re.findall(r'src="([^"]+\.js)"', t)
out.append("FL js: " + str(js))
for j in js[:4]:
    u = j if j.startswith("http") else "https://vendor.myfloridamarketplace.com/" + j.lstrip("/")
    try:
        b = s.get(u).text
        out.append(f"FL js {u}: " + str(sorted(set(re.findall(r'["\'](/?api/[^"\']{3,80}|https?://[^"\']*api[^"\']{0,80})["\']', b)))[:40]))
    except Exception as e:
        out.append(f"FL js ERR {e}")
Path("data/probe/us_probe.txt").write_text("\n".join(out))
