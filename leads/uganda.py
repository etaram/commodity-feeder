"""Uganda: eGP (egpuganda.go.ug) public bid notices: reference, procuring entity, category, subject, published and
deadline dates. The list shortens long subjects, so the full subject is read from each new notice's page (cached)."""
import html
import json
import re

from .common import LEADS, clean, log, polite, rolling, today
from .sectors import classify

BASE = "https://egpuganda.go.ug"
CACHE = LEADS / "cache" / "uganda_titles.json"
CAT = {"Supplies": "goods", "Works": "works", "Non Consultancy Services": "services", "Consultancy Services": "services"}
ROW = re.compile(r'<a href="(https://egpuganda\.go\.ug/index/(\d+)_egp)" class="text-default font-weight-semibold">\s*([^<]+?)\s*'
                 r'<div class="text-muted font-size-sm">.*?</span>\s*([^<]+?)\s*</div>.*?<span class="badge[^"]*">([^<]+)</span>.*?'
                 r'<span class="text-muted">([^<]*)</span>.*?<span class="text-[^"]*">(\d{4}-\d\d-\d\d)</span>.*?'
                 r'<span class="text-[^"]*">(\d{4}-\d\d-\d\d)</span>', re.S)


def _full_title(s, url, short):
    """The notice page repeats the subject in full; take the longest text block that starts with the shortened one."""
    try:
        t = s.get(url, timeout=60).text
    except Exception:  # noqa: BLE001
        return ""
    stem = short.rstrip(". ").lower()[:40]
    best = ""
    for m in re.finditer(r">([^<>]{20,600})<", t):
        x = clean(html.unescape(m.group(1)))
        if x.lower().startswith(stem) and len(x) > len(best):
            best = x
    return best


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    titles = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    t, new, seen, page, looked = str(today()), [], set(), 1, 0
    while page <= 60:
        try:
            r = s.get(f"{BASE}/bid-notices", params={"page": page}, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("Uganda page %d: %s", page, str(e)[:120]); break
        if r.status_code != 200:
            log.warning("Uganda %s page %d", r.status_code, page); break
        got = 0
        for url, nid, ref, pe, cat, subj, pub, dl in ROW.findall(r.text):
            if nid in seen:
                continue
            seen.add(nid); got += 1
            if dl < t:
                continue
            subj = clean(html.unescape(subj))
            if subj.endswith("...") and nid not in titles and looked < 200:
                titles[nid] = _full_title(s, url, subj) or subj; looked += 1; polite(1)
            title = titles.get(nid) or subj
            sector, how = classify(title)
            new.append({
                "id": f"UG-{nid}", "source": "eGP (Uganda)", "group": "", "sector": sector, "nature": CAT.get(clean(cat), ""),
                "cpv": "", "classification": how, "country": "UGA", "buyer": clean(html.unescape(pe), 120), "title": title[:300],
                "notice_type": clean(ref, 60), "stage": "tender", "access": "Open (check eligibility in the bidding document)",
                "published": pub, "deadline": dl, "value": "", "currency": "", "link": url, "lang": "", "contact": "",
            })
        if got == 0:
            break
        page += 1
        polite(1.5)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(titles))
    rows, _ = rolling("uganda", new)
    log.info("Uganda new %d, open %d (pages %d, titles looked up %d)", len(new), len(rows), page, looked)
    return rows, {"new": len(new)}
