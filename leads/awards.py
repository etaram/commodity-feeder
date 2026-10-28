"""TED contract award notices, all sectors: who won, for how much, how many bids. Stored per publication day in
data/leads/awards/ted/YYYY-MM-DD.json; each run fetches the last 3 days and back-fills missing days (up to 12 months)."""
import datetime as dt

from .common import PRIVATE, award_days, clean, log, save_awards, session, today
from .sectors import from_cpv
from .taxonomy import match_cpv
from .ted import URL, _date, _first

FIELDS = ["publication-number", "notice-title", "buyer-name", "buyer-country", "classification-cpv", "publication-date",
          "winner-name", "winner-country", "winner-size", "total-value", "total-value-cur",
          "received-submissions-type-val", "organisation-email-buyer", "contract-nature",
          "organisation-name-tenderer", "organisation-email-tenderer", "organisation-tel-tenderer",
          "organisation-city-tenderer", "organisation-identifier-tenderer", "organisation-internet-address-tenderer",
          "organisation-country-tenderer"]
BACKFILL_DAYS_PER_RUN = 20
MIN_EUR = 50_000


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return ""


def _fetch_day(s, day):
    q = f"notice-type IN (can-standard can-social) AND PD={day:%Y%m%d}"
    rows, token, pages = [], None, 0
    while pages < 60:
        body = {"query": q, "fields": FIELDS, "limit": 250, "paginationMode": "ITERATION"}
        if token:
            body["iterationNextToken"] = token
        r = s.post(URL, json=body, timeout=120)
        if r.status_code != 200:
            log.warning("TED awards %s: %s %s", day, r.status_code, r.text[:200]); return None
        j = r.json(); batch = j.get("notices", []); pages += 1
        for n in batch:
            cpv = list(dict.fromkeys(n.get("classification-cpv") or []))
            val, cur = _num(n.get("total-value")), _first(n.get("total-value-cur"))
            if val != "" and cur == "EUR" and val < MIN_EUR:
                continue
            gid, _ = match_cpv(cpv[:1])
            wn = n.get("winner-name") or {}
            names = list(dict.fromkeys(wn.get(next(iter(wn), ""), []) if isinstance(wn, dict) else wn))
            bids = [int(x) for x in (n.get("received-submissions-type-val") or []) if str(x).isdigit()]
            pn = n.get("publication-number")
            on = n.get("organisation-name-tenderer") or {}
            onames = on.get(next(iter(on), ""), []) if isinstance(on, dict) else (on or [])
            def _l(f):
                v = n.get(f) or []
                return v if isinstance(v, list) else [v]
            em, tel, city, ident, web, ctry = (_l("organisation-email-tenderer"), _l("organisation-tel-tenderer"),
                                               _l("organisation-city-tenderer"), _l("organisation-identifier-tenderer"),
                                               _l("organisation-internet-address-tenderer"), _l("organisation-country-tenderer"))
            contacts = []
            for i, on_ in enumerate(onames[:8]):
                g = lambda lst: lst[i] if i < len(lst) else ""
                contacts.append({"name": clean(on_, 120), "country": g(ctry), "email": clean(g(em), 120),
                                 "phone": clean(g(tel), 60), "website": clean(g(web), 120), "address": clean(g(city), 80),
                                 "legal_id": clean(g(ident), 60)})
            rows.append({
                "id": f"TED-{pn}", "source": "TED", "group": gid or "", "sector": from_cpv(cpv[:1]) or "",
                "title": clean(_first(n.get("notice-title")), 200), "buyer": clean(_first(n.get("buyer-name")), 120),
                "country": ",".join(dict.fromkeys(n.get("buyer-country") or [])), "cpv": " ".join(cpv[:4]),
                "published": str(_date(n.get("publication-date")) or day),
                "winners": [clean(x, 100) for x in names[:6]],
                "winner_country": ",".join(dict.fromkeys(n.get("winner-country") or []))[:40],
                "winner_size": ",".join(dict.fromkeys(n.get("winner-size") or [])),
                "value": val, "currency": cur, "bids": max(bids) if bids else "",
                "email": _first(n.get("organisation-email-buyer")),
                "link": f"https://ted.europa.eu/en/notice/-/detail/{pn}", "contacts": contacts,
            })
        token = j.get("iterationNextToken")
        if not token or not batch:
            break
    return rows


def fetch():
    s, t = session(), today()
    have = award_days("ted")
    recent = [t - dt.timedelta(days=k) for k in range(0, 3)]
    missing = [t - dt.timedelta(days=k) for k in range(3, 366) if str(t - dt.timedelta(days=k)) not in have]
    cdf = PRIVATE / "ted_contact_days.txt"
    cdays = set(cdf.read_text().split()) if cdf.exists() else set()
    recontact = [t - dt.timedelta(days=k) for k in range(3, 366)
                 if str(t - dt.timedelta(days=k)) in have and str(t - dt.timedelta(days=k)) not in cdays]
    todo = recent + missing[:BACKFILL_DAYS_PER_RUN] + recontact[:BACKFILL_DAYS_PER_RUN]
    total = 0
    for day in todo:
        rows = _fetch_day(s, day)
        if rows is None:
            continue
        if not rows and day.weekday() < 5:
            rows = []
        save_awards("ted", rows or [{"id": f"empty-{day}", "published": str(day), "empty": True}])
        total += len(rows)
        cdays.add(str(day))
    PRIVATE.mkdir(parents=True, exist_ok=True)
    cdf.write_text("\n".join(sorted(cdays)))
    log.info("TED awards: %d days fetched, %d notices, %d days still to back-fill", len(todo), total,
             max(0, len(missing) - BACKFILL_DAYS_PER_RUN))
    return [], {"days": len(todo), "notices": total}
