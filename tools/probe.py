"""Fetch each entry in tools/probe_urls.txt and save the response under data/probe/ (for mapping new sources).
Line formats:
  name URL                         GET with requests
  name CFFI URL                    GET with curl_cffi (Chrome impersonation)
  name POST URL {json body}        POST JSON
"""
import hashlib, json, pathlib, requests
out = pathlib.Path("data/probe"); out.mkdir(parents=True, exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 commodity-feeder probe"
for line in pathlib.Path("tools/probe_urls.txt").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split(" ", 1)
    name, rest = (parts[0], parts[1]) if len(parts) == 2 else (hashlib.md5(line.encode()).hexdigest()[:8], line)
    try:
        if rest.startswith("POST "):
            url, body = rest[5:].split(" ", 1)
            r = s.post(url, json=json.loads(body), timeout=60)
        elif rest.startswith("CFFI "):
            from curl_cffi import requests as cr
            url = rest[5:]
            r = cr.get(url, impersonate="chrome", timeout=60)
        else:
            url = rest
            r = s.get(url.strip(), timeout=60)
        bodyb = r.content[:3_000_000]
        (out / f"{name}.txt").write_bytes(f"URL: {url}\nSTATUS: {r.status_code}\nTYPE: {r.headers.get('content-type')}\n\n".encode() + bodyb)
        print(name, r.status_code, len(r.content))
    except Exception as e:
        (out / f"{name}.txt").write_text(f"URL: {rest}\nERROR: {e}\n"); print(name, "ERR", e)
