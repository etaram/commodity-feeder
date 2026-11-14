"""Egypt: national e-tenders portal (etenders.gov.eg). Probe stage: reports what the portal answers to the runner
(robots.txt, home page, tender list), without relay or any challenge handling, and raises so nothing is stored."""
import re
import time

import requests

from .common import log, session

URLS = ["https://etenders.gov.eg/robots.txt", "https://etenders.gov.eg/", "https://etenders.gov.eg/Tender/DoSearch",
        "https://www.etenders.gov.eg/"]


def fetch():
    s = session()
    for u in URLS:
        try:
            r = requests.Session.get(s, u, timeout=40)
            links = sorted(set(re.findall(r'href="([^"]*(?:[Tt]ender|[Ss]earch|robots)[^"]*)"', r.text)))[:25]
            title = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
            log.info("Egypt probe %s: HTTP %s %s, %d bytes, title %r, final %s, links %s, head %r", u, r.status_code,
                     r.headers.get("content-type"), len(r.content), (title.group(1).strip()[:80] if title else ""),
                     r.url, links, r.text[:300] if "robots" in u else "")
        except Exception as e:  # noqa: BLE001
            log.warning("Egypt probe %s: %s %s", u, type(e).__name__, str(e)[:160])
        time.sleep(1)
    raise RuntimeError("Egypt: probe only, nothing stored")
