"""Australia, NSW: buy.nsw open opportunities. Probe stage: reports robots.txt and the public opportunity list as the
runner sees them; stores nothing."""
import re

import requests

from .common import log, session

URLS = ["https://buy.nsw.gov.au/opportunity/search"]


def fetch():
    s = session()
    for u in URLS:
        try:
            r = requests.Session.get(s, u, timeout=60)
            t = r.text
            log.info("NSW probe %s: HTTP %s %s %d bytes; head %r", u, r.status_code, r.headers.get("content-type"),
                     len(r.content), " ".join(t[:900].split()) if "robots" in u else "")
            if "robots" not in u:
                links = sorted(set(re.findall(r'href="([^"]*(?:opportunit|rfx|tender)[^"]*)"', t, re.I)))
                apis = sorted(set(re.findall(r'["\'](/[^"\']*(?:api|json|search)[^"\']*)["\']', t)))[:30]
                log.info("NSW probe: %d links, sample %s; api-like %s; 'Closes' %d, 'RFT' %d", len(links), links[:15], apis,
                         t.count("Close"), t.count("RFT"))
                i = t.find("/prcOpportunity/")
                blk = " ".join(t[max(0, i - 600):i + 4200].split())
                for k in range(0, len(blk), 1600):
                    log.info("NSW probe item %d: %r", k, blk[k:k + 1600])
                log.info("NSW probe pager: %s; result count %r", sorted(set(re.findall(r'href="([^"]*(?:page|start|offset)=[^"]*)"', t)))[:10],
                         " ".join((re.search(r"[^<>]{0,60}\b\d+\s+(?:results|opportunities)[^<>]{0,40}", t) or [""])[0].split()) if re.search(r"\b\d+\s+(?:results|opportunities)", t) else "")
        except Exception as e:  # noqa: BLE001
            log.warning("NSW probe %s: %s %s", u, type(e).__name__, str(e)[:160])
    raise RuntimeError("NSW: probe only, nothing stored")
