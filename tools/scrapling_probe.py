import subprocess, sys, re, time
def sh(c, t=600):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    return (r.stdout + r.stderr)[-1500:]
print(sh(f"{sys.executable} -m pip install -q 'scrapling[fetchers]' 2>&1 | tail -3"))
print(sh("scrapling install 2>&1 | tail -3", 900))
T = {
 "qatar": "https://monaqasat.mof.gov.qa/TendersOnlineServices/AvailableMinistriesTenders/1",
 "chile_site": "https://www.mercadopublico.cl/Home",
 "chile_search": "https://www.mercadopublico.cl/BuscarLicitacion",
}
from scrapling.fetchers import Fetcher, StealthyFetcher
for k, u in T.items():
    for name, fn in [("Fetcher", lambda u: Fetcher.get(u, impersonate="chrome", timeout=60, verify=False)),
                     ("Stealthy", lambda u: StealthyFetcher.fetch(u, headless=True, network_idle=True, solve_cloudflare=True, timeout=90000))]:
        t0 = time.time()
        try:
            p = fn(u)
            body = p.html_content if hasattr(p, "html_content") else str(p.body)
            ids = len(re.findall(r"TenderDetails/\d+|idlicitacion", body))
            print(f"{k} {name}: status={p.status} len={len(body)} tender_links={ids} {time.time()-t0:.0f}s title={(p.css('title::text').get() or '')[:60]!r}")
        except Exception as e:
            print(f"{k} {name}: ERR {type(e).__name__} {str(e)[:150]}")
