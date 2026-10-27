"""Fetch each URL in tools/probe_urls.txt and save the response under data/probe/ (for mapping new sources)."""
import hashlib, pathlib, re, sys, requests
out = pathlib.Path("data/probe"); out.mkdir(parents=True, exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 commodity-feeder probe"
for line in pathlib.Path("tools/probe_urls.txt").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    name, url = line.split(" ", 1) if " " in line else (hashlib.md5(line.encode()).hexdigest()[:8], line)
    try:
        r = s.get(url.strip(), timeout=60)
        body = r.content[:3_000_000]
        (out / f"{name}.txt").write_bytes(f"URL: {url}\nSTATUS: {r.status_code}\nTYPE: {r.headers.get('content-type')}\n\n".encode() + body)
        print(name, r.status_code, len(r.content))
    except Exception as e:
        (out / f"{name}.txt").write_text(f"URL: {url}\nERROR: {e}\n"); print(name, "ERR", e)
