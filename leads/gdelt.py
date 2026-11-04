"""Business news per watched country from GDELT (free, no key, updated every 15 minutes): the "what happened this
week" of the country intelligence page. One request per country per day; the result is a list of headlines with
links, never summarised by AI unless a person asks. Countries watched: partner countries, the home market, and
the emerging-market countries with the most Pursue decisions (cap WATCH_MAX).
Run inside leads.run: python -m leads.gdelt  ->  data/leads/news.csv
"""
import csv
import datetime as dt
import json
import time

from .common import LEADS, log, session, today
from .regions import region
from .dealfit import EMERGING

API = "https://api.gdeltproject.org/api/v2/doc/doc"
TERMS = ('(procurement OR tender OR "signs contract" OR "awarded" OR infrastructure OR "power plant" OR pipeline OR '
         'refinery OR mining OR fertilizer OR "port" OR "railway" OR "solar" OR "desalination" OR "hospital" OR imports OR exports OR "World Bank" OR "financing")')
WATCH_MAX = 40
CACHE = LEADS / "news"
NAMES = {}  # iso3 -> name, from countries.csv names if present, else pycountry


def _name(iso):
    if iso in NAMES:
        return NAMES[iso]
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=iso)
        NAMES[iso] = (c.common_name if hasattr(c, "common_name") else c.name) if c else iso
    except Exception:  # noqa: BLE001
        NAMES[iso] = iso
    return NAMES[iso]


def watched(prefs=None, tenders=None):
    prefs = prefs or {}
    ws = ["ISR"] + sorted((prefs.get("partners") or {}).keys())
    cnt = {}
    for r in tenders or []:
        c = (r.get("country") or "")[:3]
        if r.get("decision") == "Pursue" and region(c) in EMERGING:
            cnt[c] = cnt.get(c, 0) + 1
    for c, _ in sorted(cnt.items(), key=lambda y: -y[1]):
        if c not in ws:
            ws.append(c)
    return ws[:WATCH_MAX]


def fetch_country(s, iso):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{iso}.json"
    if f.exists():
        try:
            j = json.loads(f.read_text())
            if j.get("fetched") == str(today()):
                return j["articles"]
        except (ValueError, KeyError):
            pass
    q = f'"{_name(iso)}" {TERMS} sourcelang:english'
    try:
        r = s.get(API, params={"query": q, "mode": "ArtList", "maxrecords": 40, "format": "json", "timespan": "7d", "sort": "DateDesc"}, timeout=40)
        arts = (r.json() or {}).get("articles") or [] if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        log.warning("gdelt %s: %s", iso, type(e).__name__); arts = []
    seen, out = set(), []
    for a in arts:
        t = (a.get("title") or "").strip()
        k = t.lower()[:60]
        if not t or k in seen:
            continue
        seen.add(k)
        out.append({"title": t[:200], "url": a.get("url", ""), "domain": a.get("domain", ""),
                    "date": (a.get("seendate") or "")[:8], "lang": a.get("language", ""), "image": ""})
    f.write_text(json.dumps({"fetched": str(today()), "articles": out}, ensure_ascii=False))
    return out


def build(prefs=None, tenders=None):
    s, rows = session(), []
    ws = watched(prefs, tenders)
    for i, iso in enumerate(ws):
        arts = fetch_country(s, iso)
        for a in arts[:25]:
            d = a["date"]
            rows.append({"country": iso, "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d, **{k: a[k] for k in ("title", "domain", "url")}})
        if i < len(ws) - 1:
            time.sleep(1.5)  # GDELT asks for a polite pace
    with open(LEADS / "news.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["country", "date", "title", "domain", "url"])
        w.writeheader(); w.writerows(rows)
    log.info("gdelt news: %d headlines for %d countries", len(rows), len(ws))
    return rows


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    r = build({"partners": {"KEN": 1, "GHA": 1}}, [])
    print(len(r), r[:3])
