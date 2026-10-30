"""Inter-American Development Bank (IDB) procurement notices for projects it finances, from the IDB open data portal
(data.iadb.org, dataset "Project procurement bidding notices and notification of contract awards", CC BY 4.0).

Reads the newest notices through the portal's CKAN datastore API. Keeps notices whose deadline has not passed, and
notices without a deadline for 60 days after publication. General notices are planned tenders. Rolling store."""
import datetime as dt

from .common import clean, log, polite, rolling, session, today
from .regions import iso3
from .sectors import classify

RESOURCE = "856aabfd-2c6a-48fb-a8b8-19f3ff443618"
API = "https://data.iadb.org/api/action/datastore_search"
PAGE, MAX_PAGES = 1000, 6
SKIP = ("AWARD", "CONTRACT AWARD")  # award notifications are not open tenders


def fetch():
    s, t, new, seen = session(), today(), [], set()
    cutoff = str(t - dt.timedelta(days=150))
    for page in range(MAX_PAGES):
        try:
            r = s.get(API, params={"resource_id": RESOURCE, "limit": PAGE, "offset": page * PAGE, "sort": "publicationdate desc"}, timeout=90)
            recs = r.json()["result"]["records"]
        except Exception as e:  # noqa: BLE001
            log.warning("IDB page %d: %s", page, str(e)[:120]); break
        if not recs:
            log.warning("IDB page %d empty; response head: %s", page, str(r.text)[:300]); break
        if page == 0:
            log.info("IDB sample keys=%s first=%s", sorted(recs[0].keys()), {k: str(v)[:40] for k, v in list(recs[0].items())[:14]})
        old = 0
        for x in recs:
            pub = (x.get("publicationdate") or "")[:10]
            if pub and pub < cutoff:
                old += 1
                continue
            typ = (x.get("type") or "").upper()
            if any(k in typ for k in SKIP):
                continue
            dl = (x.get("deadline") or "")[:10]
            if dl and dl < str(t):
                continue
            if not dl and pub and pub < str(t - dt.timedelta(days=60)):
                continue
            nid = str(x.get("noticeid") or x.get("_id"))
            if nid in seen:
                continue
            seen.add(nid)
            title = clean(x.get("noticetitle") or "")
            proj = clean(x.get("projectname") or "")
            sector, method = classify(f"{title} | {proj} | {x.get('sectorenglnm') or ''}")
            new.append({
                "id": "IDB-" + nid, "source": "IDB", "group": "", "sector": sector, "nature": "", "cpv": "", "classification": method,
                "country": iso3((x.get("countryname") or "").title()) or "", "buyer": f"IDB-financed project {x.get('projectnumber') or ''}".strip(),
                "title": (title or proj)[:300], "notice_type": (x.get("type") or "Procurement notice").title(),
                "stage": "planned" if "GENERAL" in typ else "tender", "access": "International (IDB rules, member countries)",
                "published": pub, "deadline": dl, "value": "", "currency": "", "link": x.get("documenturl") or x.get("proyecturl") or "",
                "contact": "", "lang": "es" if any(c in title for c in "ñáéíóú") else "",
            })
        ds = sorted((x.get("publicationdate") or "")[:10] for x in recs)
        log.info("IDB dates min=%s max=%s sample=%s deadlines=%s", ds[0], ds[-1], [x.get("publicationdate") for x in recs[:3]], [x.get("deadline") for x in recs[:3]])
        log.info("IDB page %d: %d recs, %d old, kept so far %d", page, len(recs), old, len(new))
        if old > len(recs) * 0.6:
            break
        polite(1)
    rows, _ = rolling("iadb", new)
    log.info("IDB new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
