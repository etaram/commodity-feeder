"""Reachability probe for candidate physical-price sources, run from a GitHub Actions runner (the place the
fetchers will run). Prints status, type, size, final URL and the page title per URL. Reads public pages only."""
import re, sys, requests
URLS = [l.strip() for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderPriceProbe/1.0)", "Accept-Language": "en,*;q=0.5"}
for u in URLS:
    try:
        r = requests.get(u, headers=UA, timeout=40, allow_redirects=True)
        ct = r.headers.get("content-type", "")[:40]
        title = ""
        if "html" in ct:
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:80] if m else ""
            pdfs = len(re.findall(r"\.pdf", r.text, re.I))
            title += f" | pdf links {pdfs}"
        print(f"{r.status_code} | {len(r.content):>8} | {ct} | {u[:90]} -> {r.url[:90] if r.url != u else '='} | {title}")
    except Exception as e:
        print(f"ERR | {u[:90]} | {str(e)[:120]}")
