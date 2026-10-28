"""Ukraine: Prozorro public API. Walks the tender feed (newest changes first) for competitive open tenders that are
accepting bids, then reads each one for title, value, CPV and contacts. English names are used when provided."""
import datetime as dt
import json

from .common import CACHE, cache_empty, clean, log, polite, rolling, session, today
from .sectors import from_cpv
from .taxonomy import match_cpv

API = "https://public-api.prozorro.gov.ua/api/2.5/tenders"
OPEN_TYPES = {"aboveThreshold", "aboveThresholdEU", "aboveThresholdUA", "competitiveDialogueEU",
              "competitiveDialogueUA", "esco", "aboveThresholdUA.defense", "simple.defense", "competitiveOrdering"}
MIN_UAH = 4_000_000  # ~ USD 100k


def fetch():
    s, t = session(), today()
    cached = set()
    p = CACHE / "prozorro.jsonl"
    if p.exists():
        cached = {json.loads(line)["pz_id"] for line in p.read_text().splitlines() if line.strip()}
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=21 if cache_empty("prozorro") else 2)
    ids, url, params, pages = [], API, {"descending": 1, "limit": 1000,
                                        "opt_fields": "status,procurementMethodType,tenderPeriod"}, 0
    while url and pages < 120:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("Prozorro feed %s", r.status_code); break
        j = r.json(); data = j.get("data") or []
        if not data:
            break
        for d in data:
            if d.get("status") == "active.tendering" and d.get("procurementMethodType") in OPEN_TYPES:
                ids.append(d["id"])
        last = dt.datetime.fromisoformat(data[-1]["dateModified"])
        if last < cut:
            break
        url = (j.get("next_page") or {}).get("uri")
        polite(0.2)
    todo = [i for i in dict.fromkeys(ids) if i not in cached][:2500]
    new = []
    for i in todo:
        try:
            d = s.get(f"{API}/{i}", timeout=60).json().get("data") or {}
        except Exception as e:  # noqa: BLE001
            log.warning("Prozorro %s: %s", i, e); continue
        v = (d.get("value") or {}).get("amount") or 0
        cur = (d.get("value") or {}).get("currency") or "UAH"
        if cur == "UAH" and v < MIN_UAH:
            new.append({"id": f"PZ-{d.get('tenderID', i)}", "pz_id": i, "skip": True,
                        "deadline": ((d.get("tenderPeriod") or {}).get("endDate") or "")[:10], "published": str(t)})
            continue
        cpv = [((it.get("classification") or {}).get("id") or "")[:8] for it in d.get("items") or []]
        cpv = [c for c in dict.fromkeys(cpv) if c]
        pe = d.get("procuringEntity") or {}; cp = pe.get("contactPoint") or {}
        gid, depth = match_cpv(cpv[:1])
        new.append({
            "id": f"PZ-{d.get('tenderID', i)}", "pz_id": i, "source": "Prozorro (Ukraine)", "group": gid or "",
            "match": depth if gid else "", "sector": from_cpv(cpv[:1]) or "", "nature": d.get("mainProcurementCategory", ""),
            "cpv": " ".join(cpv[:6]), "classification": " ".join(cpv[:6]), "country": "UKR",
            "buyer": clean(pe.get("name_en") or (pe.get("identifier") or {}).get("legalName_en") or pe.get("name"), 120),
            "title": clean(d.get("title_en") or d.get("title"), 300), "notice_type": d.get("procurementMethodType", ""),
            "stage": "tender", "access": "Open to foreign bidders" if d.get("procurementMethodType", "").endswith("EU") else "National (open e-procurement)",
            "published": (d.get("dateCreated") or "")[:10], "deadline": ((d.get("tenderPeriod") or {}).get("endDate") or "")[:10],
            "value": round(v) if v else "", "currency": cur if v else "",
            "link": f"https://prozorro.gov.ua/en/tender/{d.get('tenderID', i)}",
            "contact": clean(f"{cp.get('email', '')} {cp.get('telephone', '')}", 120),
            "lang": "" if d.get("title_en") else "uk",
        })
        polite(0.15)
    rows, _ = rolling("prozorro", new, max_age_days=90)
    out = [r for r in rows if not r.get("skip")]
    log.info("Prozorro feed pages %d, candidates %d, fetched %d, open kept %d", pages, len(ids), len(todo), len(out))
    return out, {"candidates": len(ids), "fetched": len(todo)}
