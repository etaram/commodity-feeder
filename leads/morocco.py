"""Morocco: national public procurement portal (marchespublics.gov.ma, Tresorerie Generale du Royaume).
Probe stage: reports robots.txt and the public consultation list as the runner sees them; stores nothing."""
import re

import requests

from .common import clean, log, session

BASE = "https://www.marchespublics.gov.ma"


def fetch():
    s = session()
    for u in [BASE + "/robots.txt", BASE + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons"]:
        try:
            r = requests.Session.get(s, u, timeout=60)
            t = r.text
            log.info("Morocco probe %s: HTTP %s %s %d bytes; title %r; head %r", u, r.status_code,
                     r.headers.get("content-type"), len(r.content),
                     clean((re.search(r"<title[^>]*>(.*?)</title>", t, re.S) or [None, ""])[1])[:80],
                     " ".join(t[:300].split()) if "robots" in u else "")
            if "robots" not in u:
                det = re.findall(r'href="([^"]*EntrepriseDetailsConsultation[^"]*)"', t)
                log.info("Morocco probe: %d detail links, sample %s; 'Date limite' %d; PRADO_PAGESTATE %s; page-size "
                         "options %s; result count %r", len(det), det[:2], t.count("Date limite"),
                         "PRADO_PAGESTATE" in t, re.findall(r'<option[^>]*value="(\d+)"[^>]*>\s*\d+\s*</option>', t)[:12],
                         clean((re.search(r"(\d[\d\s]*)\s*r[ée]sultat", t) or [None, ""])[0])[:60])
                i = t.find("EntrepriseDetailsConsultation")
                if i > 0:
                    for k in range(0, 6000, 1500):
                        log.info("Morocco probe row html %d: %r", k, " ".join(t[i - 2500 + k:i - 1000 + k].split()))
        except Exception as e:  # noqa: BLE001
            log.warning("Morocco probe %s: %s %s", u, type(e).__name__, str(e)[:160])
    raise RuntimeError("Morocco: probe only, nothing stored")
