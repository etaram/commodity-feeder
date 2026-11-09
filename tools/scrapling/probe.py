"""Pilot probe: how each fetch layer sees the two broken price pages (plain requests, Scrapling HTTP, Scrapling browser).
Saves what came back under out/ so the parsers can be written against the real pages."""
import pathlib, sys, time, traceback
import requests
OUT = pathlib.Path("out"); OUT.mkdir(exist_ok=True)
URLS = {"giacaphe": "https://giacaphe.com/gia-ca-phe-noi-dia/",
        "merkato_list": "https://www.2merkato.com/news/capital-market-and-commodity-exchange/",
        "ecx_home": "https://www.ecx.com.et/",
        "ecx_market": "https://www.ecx.com.et/Pages/MarketData.aspx"}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def save(name, layer, status, text):
    (OUT / f"{name}.{layer}.html").write_text(text or "", encoding="utf-8")
    print(f"{name:14} {layer:8} status={status} bytes={len(text or '')}", flush=True)
for name, url in URLS.items():
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=40); save(name, "requests", r.status_code, r.text)
    except Exception as e: print(name, "requests", "ERR", repr(e)[:150])
    try:
        from scrapling.fetchers import Fetcher
        p = Fetcher.get(url, impersonate="chrome", timeout=40); save(name, "http", p.status, p.html_content if hasattr(p, "html_content") else str(p.body))
    except Exception as e: print(name, "http", "ERR", repr(e)[:200])
    try:
        from scrapling.fetchers import DynamicFetcher
        p = DynamicFetcher.fetch(url, headless=True, network_idle=True, timeout=60000); save(name, "browser", p.status, p.html_content if hasattr(p, "html_content") else str(p.body))
    except Exception as e: print(name, "browser", "ERR", repr(e)[:200]); traceback.print_exc(limit=1)
import scrapling; print("scrapling", scrapling.__version__)
