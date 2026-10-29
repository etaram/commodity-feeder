"""Why are Israeli sites unreachable from GitHub runners? Prints status / error for a sample."""
import csv
from pathlib import Path
from curl_cffi import requests as cr
rows = [r for r in csv.DictReader(open("data/israel/bodies.csv", encoding="utf-8")) if r["status"].startswith("home unreachable")][:40]
out = []
s = cr.Session(impersonate="chrome", timeout=20)
for r in rows:
    u = r["website"] if r["website"].startswith("http") else "https://" + r["website"]
    try:
        x = s.get(u, allow_redirects=True)
        out.append(f"{x.status_code} {len(x.text)} {u} -> {x.url} | {x.text[:120].strip()!r}")
    except Exception as e:
        out.append(f"ERR {type(e).__name__} {str(e)[:120]} {u}")
try:
    ip = cr.get("https://api.ipify.org", timeout=10).text
except Exception as e:
    ip = str(e)
out.insert(0, "runner ip " + ip)
Path("data/probe/il_reach.txt").write_text("\n".join(out))
