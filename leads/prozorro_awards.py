"""Ukraine Prozorro awards for the Supplier Universe: completed competitive tenders >= ~USD 100k, with the winning
supplier's EDRPOU, address, e-mail and phone (published by Prozorro). New completions each run plus a back-fill that
walks the feed backwards (pointer kept in the private cache)."""
import time

from .common import PRIVATE, log, polite, save_awards, session
from .ocds import award_rows

API = "https://public-api.prozorro.gov.ua/api/2.5/tenders"
MIN_UAH = 4_000_000
UA = {"Україна": "UKR", "Ukraine": "UKR", "": "UKR"}
PTR = PRIVATE / "prozorro_award_ptr.txt"


def _walk(s, url, params, ids, max_pages, t_end):
    pages = 0
    while url and pages < max_pages and time.time() < t_end:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            break
        j = r.json(); data = j.get("data") or []
        if not data:
            return None
        for d in data:
            v = d.get("value") or {}
            if d.get("status") == "complete" and (v.get("currency") != "UAH" or (v.get("amount") or 0) >= MIN_UAH):
                ids.append(d["id"])
        url = (j.get("next_page") or {}).get("uri")
        polite(0.2)
    return url


def fetch():
    s = session(); t_end = time.time() + 780
    ids = []
    _walk(s, API, {"descending": 1, "limit": 1000, "opt_fields": "status,value"}, ids, 6, t_end)
    back = PTR.read_text().strip() if PTR.exists() else None
    nxt = _walk(s, back or API, None if back else {"descending": 1, "limit": 1000, "opt_fields": "status,value"},
                ids, 40, time.time() + 120)
    if nxt:
        PRIVATE.mkdir(parents=True, exist_ok=True); PTR.write_text(nxt)
    rows, n = [], 0
    for i in dict.fromkeys(ids):
        if time.time() > t_end:
            break
        try:
            d = s.get(f"{API}/{i}", timeout=60).json().get("data") or {}
        except Exception:  # noqa: BLE001
            continue
        n += 1
        pe = d.get("procuringEntity") or {}
        for it in d.get("items") or []:  # Prozorro labels CPV as "ДК021"
            cl = it.get("classification") or {}
            if cl.get("scheme") in ("ДК021", "DK021"):
                cl["scheme"] = "CPV"
        d["title"] = d.get("title_en") or d.get("title")
        rel = {"ocid": d.get("tenderID", i), "date": d.get("dateModified"), "tender": d,
               "buyer": {"name": pe.get("name_en") or pe.get("name")},
               "awards": [a for a in d.get("awards") or [] if a.get("status") == "active"]}
        for a in award_rows(rel, source="Prozorro (Ukraine)", prefix="PZA", country="UKR"):
            a["winner_country"] = ",".join(UA.get(x, x) for x in (a.get("winner_country") or "UKR").split(","))
            for c in a.get("contacts") or []:
                c["country"] = UA.get(c.get("country") or "", c.get("country")) or "UKR"
            rows.append(a)
        polite(0.12)
    save_awards("prozorro", rows)
    log.info("Prozorro awards: %d candidates, %d read, %d awards", len(ids), n, len(rows))
    return [], {"candidates": len(ids), "awards": len(rows)}
