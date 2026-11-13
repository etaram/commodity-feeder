"""Ukraine: Prozorro public API. Walks the tender feed (newest changes first) for competitive open tenders that are
accepting bids, then reads each one for title, value, CPV and contacts. English names are used when provided."""
import datetime as dt
import json
import time

from .common import CACHE, cache_empty, clean, log, polite, rolling, session, today
from .sectors import from_cpv
from .taxonomy import match_cpv

API = "https://public-api.prozorro.gov.ua/api/2.5/tenders"
OPEN_TYPES = {"aboveThreshold", "aboveThresholdEU", "aboveThresholdUA", "competitiveDialogueEU",
              "competitiveDialogueUA", "esco", "aboveThresholdUA.defense", "simple.defense", "competitiveOrdering",
              "belowThreshold", "priceQuotation"}
# Owner, 13 Nov 2026: every segment and size (target 1M open opportunities). No value floor: the value is kept on the
# row and the panel filters by it. Below-threshold and price-quotation notices are national (Ukrainian) buys.
FEED_FIELDS = ("status,procurementMethodType,tenderPeriod,title,title_en,value,procuringEntity,tenderID,items,"
               "mainProcurementCategory,dateCreated")


def fetch():
    s, t = session(), today()
    cached = set()
    p = CACHE / "prozorro.jsonl"
    if p.exists():
        # rows skipped by the former value floor are read again (they were cached as {"skip": true})
        cached = {r["pz_id"] for r in (json.loads(x) for x in p.read_text().splitlines() if x.strip()) if not r.get("skip")}
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45 if len(cached) < 20000 else 2)
    ids, url, params, pages = [], API, {"descending": 1, "limit": 1000, "opt_fields": FEED_FIELDS}, 0
    feed = {}
    t_feed = time.time()
    while url and pages < 400 and time.time() - t_feed < 600:
        r = s.get(url, params=params, timeout=90); params = None; pages += 1
        if r.status_code != 200:
            log.warning("Prozorro feed %s", r.status_code); break
        j = r.json(); data = j.get("data") or []
        if not data:
            break
        for d in data:
            if d.get("status") == "active.tendering" and d.get("procurementMethodType") in OPEN_TYPES:
                ids.append(d["id"])
                if d.get("title"):
                    feed[d["id"]] = d
        last = dt.datetime.fromisoformat(data[-1]["dateModified"])
        if last < cut:
            break
        url = (j.get("next_page") or {}).get("uri")
        polite(0.2)
    todo = [i for i in dict.fromkeys(ids) if i not in cached]
    new, t0, fetched = [], time.time(), 0
    for i in todo:
        d = feed.get(i)
        if d is None:   # the feed did not carry the fields: read the tender (bounded)
            if time.time() - t0 > 300 or fetched >= 1500:
                continue
            try:
                d = s.get(f"{API}/{i}", timeout=60).json().get("data") or {}
                fetched += 1
                polite(0.15)
            except Exception as e:  # noqa: BLE001
                log.warning("Prozorro %s: %s", i, e); continue
        new.append(_row(d, i))
    rows, _ = rolling("prozorro", new, max_age_days=90)
    out = [r for r in rows if not r.get("skip")]
    log.info("Prozorro feed pages %d, candidates %d, from feed %d, read one by one %d, open kept %d", pages, len(ids),
             sum(1 for i in todo if i in feed), fetched, len(out))
    return out, {"candidates": len(ids), "from_feed": sum(1 for i in todo if i in feed), "fetched": fetched}


def _row(d, i):
    v = (d.get("value") or {}).get("amount") or 0
    cur = (d.get("value") or {}).get("currency") or "UAH"
    cpv = [((it.get("classification") or {}).get("id") or "")[:8] for it in d.get("items") or []]
    cpv = [c for c in dict.fromkeys(cpv) if c]
    pe = d.get("procuringEntity") or {}; cp = pe.get("contactPoint") or {}
    gid, depth = match_cpv(cpv[:1])
    typ = d.get("procurementMethodType", "")
    return {
        "id": f"PZ-{d.get('tenderID', i)}", "pz_id": i, "source": "Prozorro (Ukraine)", "group": gid or "",
        "match": depth if gid else "", "sector": from_cpv(cpv[:1]) or "", "nature": d.get("mainProcurementCategory", ""),
        "cpv": " ".join(cpv[:6]), "classification": " ".join(cpv[:6]), "country": "UKR",
        "buyer": clean(pe.get("name_en") or (pe.get("identifier") or {}).get("legalName_en") or pe.get("name"), 120),
        "title": clean(d.get("title_en") or d.get("title"), 300), "notice_type": typ,
        "stage": "tender", "access": "Open to foreign bidders" if typ.endswith("EU") else "National (open e-procurement)",
        "published": (d.get("dateCreated") or "")[:10], "deadline": ((d.get("tenderPeriod") or {}).get("endDate") or "")[:10],
        "value": round(v) if v else "", "currency": cur if v else "",
        "link": f"https://prozorro.gov.ua/en/tender/{d.get('tenderID', i)}",
        "contact": clean(f"{cp.get('email', '')} {cp.get('telephone', '')}", 120),
        "lang": "" if d.get("title_en") else "uk",
    }
