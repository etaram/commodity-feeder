import subprocess, sys, re
def sh(c, t=900): return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
sh(f"{sys.executable} -m pip install -q 'scrapling[fetchers]'"); sh("scrapling install")
from scrapling.fetchers import Fetcher, StealthyFetcher
def clean(b): return re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", b, flags=re.S))
def look(tag, u, stealth=False, n=1500):
    try:
        p = StealthyFetcher.fetch(u, headless=True, network_idle=True, timeout=90000) if stealth else Fetcher.get(u, impersonate="chrome", timeout=60, verify=False)
        b = p.html_content; t = clean(b)
        print(f"### {tag} {u} st={p.status} len={len(b)} tables={b.lower().count('<table')} tr={b.lower().count('<tr')}", flush=True)
        print("LINKS", sorted(set(re.findall(r'href=["\']([^"\']*(?:ender|Tender|TND|tnd|notice|Notice|bid)[^"\']*)["\']', b)))[:25], flush=True)
        print("TEXT", t[:n], flush=True); return b
    except Exception as e:
        print(f"### {tag} ERR {str(e)[:120]}", flush=True)
b = look("BH main", "https://tenderboard.gov.bh/Tenders/Tenders", True)
look("BH etendering", "https://etendering.tenderboard.gov.bh/", True)
look("BH etendering list", "https://etendering.tenderboard.gov.bh/Tenders/Tenders", True)
for u in ["https://www.capt.gov.kw/", "https://www.capt.gov.kw/en/tenders/", "https://www.capt.gov.kw/ar/tenders/"]:
    look("KW", u, True, 1200)
look("MY", "https://myprocurement.treasury.gov.my/", False, 800)
look("MY tenders", "https://myprocurement.treasury.gov.my/tender", False, 800)
