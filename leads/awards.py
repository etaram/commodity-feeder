"""TED contract award notices (supplies) for the commodity groups: who won, for how much, how many bids.
Cached by month in data/leads/awards/YYYY-MM.json; the current and previous month are refreshed every run,
older months are back-filled a few at a time up to 12 months."""
import calendar
import datetime as dt
import json

from .common import LEADS, clean, log, session, today
from .taxonomy import GROUPS, match_cpv
from .ted import URL, _date, _first

CACHE = LEADS / "awards"
FIELDS = ["publication-number", "notice-title", "buyer-name", "buyer-country", "classification-cpv", "publication-date",
          "winner-name", "winner-country", "winner-size", "total-value", "total-value-cur",
          "received-submissions-type-val", "organisation-email-buyer", "contract-nature"]
BACKFILL_PER_RUN = 3


def _month_list(n=12):
    t = today().replace(day=1); out = []
    for _ in range(n):
        out.append(t); t = (t - dt.timedelta(days=1)).replace(day=1)
    return out


def _fetch_month(s, m, cpvs):
    last = m.replace(day=calendar.monthrange(m.year, m.month)[1])
    q = (f"classification-cpv IN ({' '.join(cpvs)}) AND notice-type IN (can-standard) AND contract-nature IN (supplies) "
         f"AND PD>={m:%Y%m%d} AND PD<={last:%Y%m%d}")
    rows, page = [], 1
    while page <= 60:
        r = s.post(URL, json={"query": q, "fields": FIELDS, "limit": 250, "page": page}, timeout=120)
        if r.status_code != 200:
            log.warning("TED awards %s: %s %s", m, r.status_code, r.text[:200]); return None
        batch = r.json().get("notices", [])
        for n in batch:
            cpv = list(dict.fromkeys(n.get("classification-cpv") or []))
            gid, depth = match_cpv(cpv[:1])
            if not gid:
                continue
            wn = n.get("winner-name") or {}
            names = list(dict.fromkeys(wn.get(next(iter(wn), ""), []) if isinstance(wn, dict) else wn))
            bids = [int(x) for x in (n.get("received-submissions-type-val") or []) if str(x).isdigit()]
            val = n.get("total-value")
            rows.append({
                "pn": n.get("publication-number"), "group": gid, "depth": depth,
                "title": clean(_first(n.get("notice-title")), 250), "buyer": clean(_first(n.get("buyer-name")), 120),
                "country": ",".join(dict.fromkeys(n.get("buyer-country") or [])), "cpv": " ".join(cpv[:4]),
                "published": str(_date(n.get("publication-date")) or ""),
                "winners": [clean(x, 100) for x in names[:6]],
                "winner_country": ",".join(dict.fromkeys(n.get("winner-country") or []))[:40],
                "winner_size": ",".join(dict.fromkeys(n.get("winner-size") or [])),
                "value": float(val) if isinstance(val, (int, float)) or str(val or "").replace(".", "", 1).isdigit() else "",
                "currency": _first(n.get("total-value-cur")), "bids": max(bids) if bids else "",
                "email": _first(n.get("organisation-email-buyer")),
            })
        if len(batch) < 250:
            break
        page += 1
    return rows


def fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    cpvs = sorted({c for g in GROUPS for c in g["cpv"]})
    s = session(); done, back = 0, 0
    for i, m in enumerate(_month_list()):
        f = CACHE / f"{m:%Y-%m}.json"
        if i >= 2 and f.exists():
            continue
        if i >= 2:
            if back >= BACKFILL_PER_RUN:
                continue
            back += 1
        rows = _fetch_month(s, m, cpvs)
        if rows is not None:
            f.write_text(json.dumps(rows, ensure_ascii=False)); done += 1
            log.info("awards %s: %d", m, len(rows))
    for f in CACHE.glob("*.json"):  # keep 12 months
        if f.stem < f"{_month_list()[-1]:%Y-%m}":
            f.unlink()
    return [], {"months_refreshed": done}
