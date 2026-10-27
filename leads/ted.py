"""EU tenders from TED (Tenders Electronic Daily) Search API v3 - free, no key.
Open contract notices for SUPPLIES whose CPV falls in one of the commodity groups."""
import datetime as dt

from .common import clean, log, session, today
from .taxonomy import GROUPS, match_cpv

URL = "https://api.ted.europa.eu/v3/notices/search"
FIELDS_FULL = ["publication-number", "notice-title", "buyer-name", "buyer-country", "classification-cpv",
               "publication-date", "notice-type", "deadline-receipt-tender-date-lot", "estimated-value-lot",
               "estimated-value-cur-lot", "contract-nature", "place-of-performance", "organisation-email-buyer",
               "organisation-tel-buyer", "organisation-city-buyer"]
FIELDS_MIN = ["publication-number", "notice-title", "buyer-name", "buyer-country", "classification-cpv",
              "publication-date", "notice-type", "deadline-receipt-tender-date-lot", "estimated-value-lot",
              "contract-nature"]
LOOKBACK_DAYS = 21


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


def fetch():
    cpvs = sorted({c for g in GROUPS for c in g["cpv"]})
    since = (today() - dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    queries = [
        f"classification-cpv IN ({' '.join(cpvs)}) AND notice-type IN (cn-standard cn-social) "
        f"AND contract-nature IN (supplies) AND PD>={since}",
        f"classification-cpv IN ({' '.join(cpvs)}) AND notice-type IN (cn-standard) AND PD>={since}",
    ]
    s = session()
    notices, used = [], None
    for q in queries:
        for fields in (FIELDS_FULL, FIELDS_MIN):
            page, got, ok = 1, [], True
            while page <= 40:
                r = s.post(URL, json={"query": q, "fields": fields, "limit": 250, "page": page}, timeout=90)
                if r.status_code != 200:
                    log.warning("TED %s: %s", r.status_code, r.text[:300]); ok = False; break
                j = r.json(); batch = j.get("notices", [])
                got += batch
                if len(batch) < 250:
                    break
                page += 1
            if ok:
                notices, used = got, (q, fields); break
        if used:
            break
    log.info("TED notices: %d", len(notices))
    rows, t = [], today()
    for n in notices:
        nature = n.get("contract-nature") or []
        if nature and "supplies" not in nature:
            continue
        cpv = list(dict.fromkeys(n.get("classification-cpv") or []))
        gid, depth = match_cpv(cpv)
        if not gid:
            continue
        dls = sorted(d for d in (_date(x) for x in (n.get("deadline-receipt-tender-date-lot") or [])) if d)
        future = [d for d in dls if d >= t]
        if dls and not future:
            continue
        deadline = future[0] if future else None
        vals = []
        for v in n.get("estimated-value-lot") or []:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        cur = _first(n.get("estimated-value-cur-lot")) or ("EUR" if vals else "")
        title = clean(_first(n.get("notice-title")))
        pn = n.get("publication-number", "")
        rows.append({
            "id": f"TED-{pn}", "source": "TED (EU)", "group": gid,
            "country": ",".join(dict.fromkeys(n.get("buyer-country") or [])),
            "buyer": clean(_first(n.get("buyer-name")), 120), "title": title[:300],
            "classification": " ".join(cpv[:6]), "notice_type": n.get("notice-type", ""),
            "published": str(_date(n.get("publication-date")) or ""), "deadline": str(deadline or ""),
            "value": round(sum(vals)) if vals else "", "currency": cur if vals else "",
            "link": f"https://ted.europa.eu/en/notice/-/detail/{pn}", "contact": clean(" ".join(dict.fromkeys((n.get("organisation-email-buyer") or [])[:1] +
                                                      (n.get("organisation-tel-buyer") or [])[:1])), 120),
            "match": depth,
        })
    return rows, {"query": used[0] if used else "", "notices": len(notices)}
