"""Save sample pages of candidate price sources (public pages only) so their parsers can be written offline."""
import hashlib, re, sys, requests, pathlib
out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderPriceProbe/1.0)", "Accept-Language": "en,*;q=0.5"}
for line in open(sys.argv[1]):
    line = line.strip()
    if not line or line.startswith("#"): continue
    name, u = line.split(" ", 1)
    try:
        r = requests.get(u, headers=UA, timeout=60)
        ext = ".pdf" if "pdf" in r.headers.get("content-type", "") else ".json" if "json" in r.headers.get("content-type", "") else ".xlsx" if "sheet" in r.headers.get("content-type", "") else ".html"
        (out / f"{name}{ext}").write_bytes(r.content[:6_000_000])
        print(name, r.status_code, len(r.content), r.url[:100])
    except Exception as e:
        print(name, "ERR", str(e)[:100])
