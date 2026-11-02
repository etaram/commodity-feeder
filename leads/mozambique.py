"""Mozambique: UFSA (Unidade Funcional de Supervisao das Aquisicoes) list of open tenders on its home page.
Keeps public and international tenders; limited tenders and direct awards are invitation-only."""
import html
import re

from .common import clean, log, rolling, today
from .sectors import classify

BASE = "https://www.ufsa.gov.mz/"
ITEM = re.compile(r'<label class="label_roll"><br>([^:<]+):\s*([^<]+)<br><label class=lbl_objecto>([^<]+)</label><br>([^<]+)<br>'
                  r'VALIDADE:\s*<u>(\d{4}-\d\d-\d\d)</u><br><a href=\'([^\']+)\'', re.S)


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    t, new = str(today()), []
    try:
        body = s.get(BASE, timeout=60).text
    except Exception as e:  # noqa: BLE001
        log.warning("Mozambique: %s", str(e)[:120]); body = ""
    for kind, ref, obj, ent, dl, link in ITEM.findall(body):
        kind = clean(kind).upper()
        if dl < t or "LIMITADO" in kind or "AJUSTE" in kind:
            continue
        title = clean(html.unescape(obj))
        sector, how = classify(title)
        new.append({
            "id": "MZ-" + re.sub(r"[^\w]", "", ref)[:50], "source": "UFSA (Mozambique)", "group": "", "sector": sector,
            "nature": "", "cpv": "", "classification": how, "country": "MOZ", "buyer": clean(html.unescape(ent), 120),
            "title": title[:300], "notice_type": f"{kind.title()} {clean(ref)}"[:60], "stage": "tender",
            "access": "International" if "INTERNACIONAL" in kind else "National (foreign firms may bid)",
            "published": "", "deadline": dl, "value": "", "currency": "", "link": BASE + link.replace(" ", "%20"),
            "lang": "pt", "contact": "",
        })
    rows, _ = rolling("mozambique", new)
    log.info("Mozambique new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
