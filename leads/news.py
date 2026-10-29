"""Press context for the best deals: GDELT DOC 2.0 (free, official API, 65 languages).

For every Pursue deal and the top Watch deals, search the buyer's name in world press (last 120 days).
Appends three columns to deal_calc.csv (press_count, press_top, press_link) and writes press.csv with
up to 3 linked articles per deal. Buyer results are cached for 7 days. No scraping - API only.
Run after merge: python -m leads.news
"""
import csv
import datetime as dt
import json
import re
import time

from .common import LEADS, log, session

DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
CACHE = LEADS / "cache" / "news.json"
GENERIC = re.compile(r"\b(ministry|department|agency|municipality|city|office|directorate|general|public|national|"
                     r"state|royal|федераль|محافظة|municipal|regional|council|authority|government)\b", re.I)


def _query(buyer):
    b = re.sub(r"[\"'()\[\]{}|]", " ", buyer).strip()
    b = re.sub(r"\s+", " ", b)[:80]
    if not b or len(b) < 6:
        return ""
    # a generic buyer name alone ("Ministry of Health") matches the whole world's press - too noisy
    if GENERIC.search(b) and len(b.split()) <= 3:
        return ""
    return f'"{b}"'


def _fetch(s, q):
    try:
        r = s.get(DOC, params={"query": q, "mode": "artlist", "format": "json", "maxrecords": 8,
                               "timespan": "120d", "sort": "datedesc"}, timeout=12)
        arts = (r.json() or {}).get("articles", [])
    except Exception as e:  # noqa: BLE001
        log.warning("gdelt %s: %s", q[:40], type(e).__name__)
        return None
    out, seen = [], set()
    for a in arts:
        t = (a.get("title") or "").strip()
        k = re.sub(r"\W+", "", t.lower())[:60]
        if not t or k in seen:
            continue
        seen.add(k)
        out.append({"title": t[:200], "url": a.get("url", ""), "domain": a.get("domain", ""),
                    "date": (a.get("seendate") or "")[:8], "lang": a.get("language", "")})
    return out


def run(max_queries=120, budget_s=420):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cut = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    dc = LEADS / "deal_calc.csv"
    if not dc.exists():
        log.info("news: no deal_calc.csv"); return
    rows = list(csv.DictReader(open(dc, encoding="utf-8")))
    cols = rows[0].keys() if rows else []
    todo = [r for r in rows if r.get("decision") == "Pursue"] + \
           [r for r in rows if r.get("decision") == "Watch"][:300]
    s = session()
    press, q_done = [], 0
    t_end = time.time() + budget_s
    for r in todo:
        q = _query(r.get("buyer", ""))
        key = q or r.get("buyer", "")[:60]
        hit = cache.get(key)
        if q and (not hit or hit["ts"] < cut) and q_done < max_queries and time.time() < t_end:
            arts = _fetch(s, q)
            q_done += 1
            time.sleep(5.2)  # GDELT asks for at most one request every 5 seconds
            if arts is not None:
                hit = {"ts": dt.date.today().isoformat(), "articles": arts}
                cache[key] = hit
        arts = (hit or {}).get("articles", [])
        r["press_count"] = len(arts) if q else ""
        r["press_top"] = arts[0]["title"] if arts else ""
        r["press_link"] = arts[0]["url"] if arts else ""
        for a in arts[:3]:
            press.append({"id": r["id"], "buyer": r.get("buyer", "")[:120], "country": r.get("country", ""),
                          "date": a["date"], "headline": a["title"], "domain": a["domain"], "link": a["url"]})
    for r in rows:
        r.setdefault("press_count", ""); r.setdefault("press_top", ""); r.setdefault("press_link", "")
    out_cols = list(cols) + ["press_count", "press_top", "press_link"]
    with open(dc, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_cols)
        w.writeheader(); w.writerows(rows)
    with open(LEADS / "press.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "buyer", "country", "date", "headline", "domain", "link"])
        w.writeheader(); w.writerows(press)
    CACHE.parent.mkdir(exist_ok=True, parents=True)
    CACHE.write_text(json.dumps(cache))
    log.info("news: %d deals checked, %d GDELT queries, %d linked articles", len(todo), q_done, len(press))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    run()
