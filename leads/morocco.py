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
                i = t.find("p-objet")
                j = t.find('class="contentColumn" onclick', i)
                item = " ".join(t[i:j if j > 0 else i + 9000].split())
                for k in range(0, min(len(item), 9000), 1400):
                    log.info("Morocco probe item %d: %r", k, item[k:k + 1400])
                names = re.findall(r'<(?:input|select)[^>]*name="([^"]+)"', t)
                log.info("Morocco probe form fields (%d): %s", len(names), [n for n in names if re.search(r"(?i)date|prado|page|sort|tri|categ|etat|statut|limit", n)][:60])
                log.info("Morocco probe sort/ordre links: %s", re.findall(r'id="([^"]*(?:sort|Sort|tri|Tri)[^"]*)"', t)[:20])
        except Exception as e:  # noqa: BLE001
            log.warning("Morocco probe %s: %s %s", u, type(e).__name__, str(e)[:160])
    raise RuntimeError("Morocco: probe only, nothing stored")
