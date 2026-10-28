"""EU tenders from TED (Tenders Electronic Daily) Search API v3 - free, no key.

All open calls for competition (supplies, works, services; every CPV), kept in a rolling cache so each run only
fetches the last few days. Each notice gets a sector (from its main CPV) and, where it applies, a commodity group.
Notices with a known estimated value below MIN_EUR are dropped (low value for international bidders).
"""
import datetime as dt
import html

from .common import cache_empty, clean, log, rolling, session, today
from .sectors import from_cpv, nature_of_cpv
from .taxonomy import match_cpv

URL = "https://api.ted.europa.eu/v3/notices/search"
FIELDS = ["publication-number", "notice-title", "buyer-name", "buyer-country", "classification-cpv",
          "publication-date", "notice-type", "deadline-receipt-tender-date-lot", "estimated-value-lot",
          "estimated-value-cur-lot", "contract-nature", "organisation-email-buyer", "organisation-tel-buyer"]
NOTICE_TYPES = "cn-standard cn-social cn-desg pin-cfc-standard pin-cfc-social"
MIN_EUR = 100_000


def _first(v):
    if isinstance(v, dict):
        for k in ("eng", "ENG"):
            if k in v:
                return _first(v[k])
        return _first(next(iter(v.values()), ""))
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def _date(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _search(s, query, max_pages=200):
    out, token, pages = [], None, 0
    while pages < max_pages:
        body = {"query": query, "fields": FIELDS, "limit": 250, "paginationMode": "ITERATION"}
        if token:
            body["iterationNextToken"] = token
        r = s.post(URL, json=body, timeout=120)
        if r.status_code != 200:
            log.warning("TED %s: %s", r.status_code, r.text[:300]); break
        j = r.json(); batch = j.get("notices", []); out += batch; pages += 1
        if pages == 1:
            log.info("TED total matching notices: %s", j.get("totalNoticeCount"))
        token = j.get("iterationNextToken")
        if not token or not batch:
            break
    return out, pages


def _row(n, t):
    cpv = list(dict.fromkeys(n.get("classification-cpv") or []))
    dls = sorted(d for d in (_date(x) for x in (n.get("deadline-receipt-tender-date-lot") or [])) if d)
    future = [d for d in dls if d >= t]
    if dls and not future:
        return None
    vals = []
    for v in n.get("estimated-value-lot") or []:
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            pass
    cur = _first(n.get("estimated-value-cur-lot")) or ("EUR" if vals else "")
    if vals and cur == "EUR" and sum(vals) < MIN_EUR:
        return None
    gid, depth = match_cpv(cpv[:1])
    pn = n.get("publication-number", "")
    nt = n.get("notice-type", "")
    return {
        "id": f"TED-{pn}", "source": "TED (EU)", "group": gid or "", "match": depth if gid else "",
        "sector": from_cpv(cpv[:1]) or "", "nature": (n.get("contract-nature") or [nature_of_cpv(cpv)])[0],
        "cpv": " ".join(cpv[:6]), "classification": " ".join(cpv[:6]),
        "country": ",".join(dict.fromkeys(n.get("buyer-country") or [])),
        "buyer": clean(_first(n.get("buyer-name")), 120),
        "title": clean(html.unescape(html.unescape(_first(n.get("notice-title")))))[:300],
        "notice_type": nt, "stage": "tender", "access": "GPA/EU open",
        "published": str(_date(n.get("publication-date")) or ""), "deadline": str(future[0] if future else ""),
        "value": round(sum(vals)) if vals else "", "currency": cur if vals else "",
        "link": f"https://ted.europa.eu/en/notice/-/detail/{pn}",
        "contact": clean(" ".join(dict.fromkeys((n.get("organisation-email-buyer") or [])[:1] +
                                                (n.get("organisation-tel-buyer") or [])[:1])), 120),
    }


def fetch():
    t = today()
    days = 21 if cache_empty("ted") else 3
    since = (t - dt.timedelta(days=days)).strftime("%Y%m%d")
    notices, pages = _search(session(), f"notice-type IN ({NOTICE_TYPES}) AND PD>={since}")
    new = [r for r in (_row(n, t) for n in notices) if r]
    rows, size = rolling("ted", new)
    log.info("TED fetched %d notices (%d pages, %d days) -> %d new rows, cache %d open (%d bytes)",
             len(notices), pages, days, len(new), len(rows), size)
    return rows, {"fetched": len(notices), "days": days, "cache": len(rows)}
