"""Kenya: Public Procurement Information Portal (tenders.go.ke) active tenders API."""
import datetime as dt

from .common import clean, log, polite, rolling, today
from .sectors import classify

URL = "https://tenders.go.ke/api/active-tenders"
CAT = {1: "goods", 2: "works", 3: "services", 4: "services"}


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    t, new, page = today(), [], 1
    while page <= 60:
        r = s.get(URL, params={"page": page}, timeout=60)
        if r.status_code != 200:
            log.warning("Kenya %s page %d", r.status_code, page); break
        j = r.json(); data = j.get("data") or []
        for x in data:
            close = (x.get("close_at") or "")[:10]
            if close and close < str(t):
                continue
            pe = (x.get("pe") or (x.get("created_by") or {}).get("pe") or {})
            title = clean(x.get("title"))
            sector, method = classify(title)
            new.append({
                "id": f"KE-{x.get('id')}", "source": "PPIP (Kenya)", "group": "", "sector": sector,
                "nature": CAT.get(x.get("procurement_category_id"), ""), "cpv": "", "classification": method,
                "country": "KEN", "buyer": clean(pe.get("name"), 120), "title": title[:300],
                "notice_type": clean(x.get("tender_ref"), 60), "stage": "tender", "access": "National (AGPO/local preference)",
                "published": (x.get("published_at") or "")[:10], "deadline": close, "value": "", "currency": "",
                "link": f"https://tenders.go.ke/tenders/{x.get('id')}", "lang": "",
                "contact": clean(f"{pe.get('email', '')} {pe.get('telephone', '')}", 120),
            })
        if not j.get("next_page_url"):
            break
        page += 1
        polite(1.5)
    rows, _ = rolling("kenya", new)
    log.info("Kenya new %d, open %d (pages %d)", len(new), len(rows), page)
    return rows, {"new": len(new)}
