"""Google Trends search interest for the top Market Signals (product x country), via pytrends.

pytrends is unofficial: Google rate-limits it (HTTP 429), more so from cloud IPs. This module is built to fail soft:
small weekly batch, a pause between calls, back-off on 429, stop after repeated blocks, and keep last week's values for
anything it could not refresh. It is a stopgap until the official Google Trends API (alpha, access requested) arrives;
swap fetch_series() for the official client then, nothing else changes.

Search terms are Google *topics* (language independent: "Coffee" the topic matches searches in any language), found
once with suggestions() and cached. Only consumer-facing groups are queried; for industrial B2B goods search interest
says little.

Output: 'Trends' tab of the Leads Engine sheet (RAW) and data/leads/trends.csv.
  python -m leads.trends            refresh (default 40 pairs)
  python -m leads.trends 10         refresh 10 pairs (test)
"""
import csv
import datetime as dt
import json
import random
import sys
import time
import urllib.parse
from pathlib import Path

from .common import LEADS

CACHE = LEADS / "cache" / "trends.json"
OUT = LEADS / "trends.csv"
MARKETS = LEADS / "markets.csv"

# product prefix (first part of the HS description) -> plain search term used to find the Google topic
TERMS = {
    "Coffee": "Coffee", "Dairy produce": "Butter", "Fish fillets": "Tuna", "Meat": "Beef", "Meat and edible offal": "Chicken meat",
    "Nuts, edible": "Nut", "Spices": "Spice", "Sugars": "Sugar", "Vegetable oils": "Vegetable oil", "Cereals": "Rice",
    "Wheat or meslin flour": "Flour", "Tobacco": "Tobacco", "Alcohols": "Ethanol", "Vegetables, alliaceous": "Onion",
    "Crustaceans": "Shrimp", "Oil seeds": "Sesame", "Salt (including table salt and denatured salt)": "Salt",
}
# Market Signals country names that pycountry does not resolve on its own
ISO2 = {"USA": "US", "Rep. of Korea": "KR", "Korea, Rep.": "KR", "Russian Federation": "RU", "Viet Nam": "VN", "Türkiye": "TR",
        "Turkey": "TR", "Iran": "IR", "China, Hong Kong SAR": "HK", "Taiwan": "TW", "Czechia": "CZ", "United Kingdom": "GB",
        "United Arab Emirates": "AE", "Saudi Arabia": "SA", "Bolivia (Plurinational State of)": "BO", "Dem. Rep. of the Congo": "CD"}


def _iso2(name):
    if name in ISO2:
        return ISO2[name]
    try:
        import pycountry
        return pycountry.countries.lookup(name).alpha_2
    except Exception:  # noqa: BLE001
        try:
            import pycountry
            return pycountry.countries.search_fuzzy(name)[0].alpha_2
        except Exception:  # noqa: BLE001
            return ""


def _pairs(limit):
    rows = list(csv.DictReader(open(MARKETS, encoding="utf-8")))
    rows.sort(key=lambda r: -float(r.get("signal_score") or 0))
    seen, out = set(), []
    for r in rows:
        prefix = r["product"].split(";")[0].strip()
        term = TERMS.get(prefix)
        geo = _iso2(r["country"])
        if not term or not geo or (term, geo) in seen:
            continue
        seen.add((term, geo))
        out.append({"term": term, "product": prefix, "hs6": r["hs6"], "country": r["country"], "geo": geo,
                    "signal_score": r.get("signal_score", ""), "growth_pct": r.get("growth_pct", "")})
        if len(out) >= limit:
            break
    return out


class Blocked(Exception):
    pass


def _client():
    from pytrends.request import TrendReq
    return TrendReq(hl="en-US", tz=0, timeout=(10, 30), retries=0)


def topic_id(py, term, cache):
    """Google topic mid for a term (e.g. Coffee -> /m/02vqfm), cached forever."""
    topics = cache.setdefault("topics", {})
    if term in topics:
        return topics[term]
    try:
        sug = py.suggestions(term)
    except Exception as e:  # noqa: BLE001
        if "429" in str(e):
            raise Blocked(str(e)) from e
        sug = []
    mid = next((s["mid"] for s in sug if s.get("title", "").lower() == term.lower()), sug[0]["mid"] if sug else "")
    topics[term] = mid or term
    return topics[term]


def _brightdata():
    """Bright Data's Google Trends API (paid per successful request, cents each; github.com/luminati-io/google-trends-api).
    Used when BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE are set in the environment or in the Supplier Universe sheet,
    tab Config (the same store as WEB_INDEX_KEY). Otherwise pytrends as before."""
    import os
    key, zone = os.environ.get("BRIGHTDATA_API_KEY", ""), os.environ.get("BRIGHTDATA_ZONE", "")
    if not (key and zone):
        try:
            from .push import UNIVERSE_SHEET, Sheets
            cfg = {r[0]: r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B12") if len(r) > 1}
            key, zone = cfg.get("BRIGHTDATA_API_KEY", key), cfg.get("BRIGHTDATA_ZONE", zone)
        except Exception:  # noqa: BLE001
            pass
    return (key, zone) if key and zone else None


def fetch_series_brightdata(creds, term, geo):
    """Interest over time through Bright Data: monthly means of the 12-month weekly series, oldest first.
    The parsed JSON shape is taken from the response as it comes; unknown shapes are logged, never guessed."""
    import requests
    key, zone = creds
    url = "https://trends.google.com/trends/explore?" + urllib.parse.urlencode({"q": term, "geo": geo, "date": "today 12-m", "hl": "en", "brd_trends": "timeseries", "brd_json": "1"})
    r = requests.post("https://api.brightdata.com/request", json={"zone": zone, "url": url, "format": "raw"},
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=90)
    if r.status_code != 200:
        raise Blocked(f"brightdata {r.status_code}: {r.text[:120]}")
    j = r.json()
    pts = None
    for path in (("timeseries",), ("timelineData",), ("default", "timelineData"), ("interest_over_time", "timelineData")):
        cur = j
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if isinstance(cur, list) and cur:
            pts = cur; break
    if pts is None:
        log.warning("brightdata trends: unknown shape, keys %s", list(j)[:8] if isinstance(j, dict) else type(j).__name__)
        return []
    vals = []
    for x in pts:
        v = x.get("value") if isinstance(x, dict) else None
        v = v[0] if isinstance(v, list) and v else v
        t = x.get("time") or x.get("date") or x.get("formattedTime") if isinstance(x, dict) else None
        try:
            vals.append((str(t), float(v)))
        except (TypeError, ValueError):
            continue
    if not vals:
        return []
    # monthly means from weekly points: time is an epoch string or a date
    by_m = {}
    for t, v in vals:
        try:
            d = dt.datetime.utcfromtimestamp(int(t)) if t.isdigit() else dt.datetime.fromisoformat(t[:10])
        except ValueError:
            continue
        by_m.setdefault(d.strftime("%Y-%m"), []).append(v)
    return [round(sum(v) / len(v), 1) for _, v in sorted(by_m.items())][-12:]


def fetch_series(py, kw, geo):
    """12 months of weekly interest (0-100) for one keyword/topic in one country -> monthly means, oldest first."""
    try:
        py.build_payload([kw], timeframe="today 12-m", geo=geo)
        df = py.interest_over_time()
    except Exception as e:  # noqa: BLE001
        if "429" in str(e) or "Too Many" in str(e):
            raise Blocked(str(e)) from e
        raise
    if df is None or df.empty or kw not in df:
        return []
    m = df[kw].resample("MS").mean().round(1)
    return [float(x) for x in m.tolist()][-12:]


def _summary(series):
    if len(series) < 6 or not any(series):
        return "", ""
    last3 = sum(series[-3:]) / 3
    prior = series[:-3]
    base = sum(prior) / len(prior) if prior else 0
    change = round((last3 - base) / base * 100, 1) if base else ""
    return change, round(last3, 1)


def main(argv=None):
    argv = argv or sys.argv[1:]
    limit = int(argv[0]) if argv and argv[0].isdigit() else 40
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    series_cache = cache.setdefault("series", {})
    pairs = _pairs(limit)
    bd = _brightdata()
    py = None if bd else _client()
    if bd:
        log.info("trends: Bright Data Google Trends API (paid per success)")
    ok = blocked = failed = 0
    strikes = 0
    for p in pairs:
        key = f"{p['term']}|{p['geo']}"
        if strikes >= 3:
            p["status"] = "skipped (rate limited)"
            continue
        try:
            if bd:
                s = fetch_series_brightdata(bd, p["term"], p["geo"])
            else:
                kw = topic_id(py, p["term"], cache)
                s = fetch_series(py, kw, p["geo"])
            series_cache[key] = {"series": s, "fetched": dt.date.today().isoformat()}
            p["status"] = "ok" if s else "no data"
            ok += 1
            strikes = 0
        except Blocked:
            blocked += 1
            strikes += 1
            p["status"] = "rate limited"
            time.sleep(60 * strikes)
        except Exception as e:  # noqa: BLE001
            failed += 1
            p["status"] = f"error: {str(e)[:80]}"
        time.sleep(random.uniform(6, 12))

    header = ["product", "search_topic", "hs6", "country", "geo", "trend_change_pct", "interest_last3m", "series_12m",
              "market_signal_score", "import_growth_pct", "fetched", "status"]
    rows = [header]
    for p in pairs:
        key = f"{p['term']}|{p['geo']}"
        c = series_cache.get(key, {})
        s = c.get("series", [])
        change, last3 = _summary(s)
        rows.append([p["product"], p["term"], p["hs6"], p["country"], p["geo"], change, last3, " ".join(str(round(x)) for x in s),
                     p["signal_score"], p["growth_pct"], c.get("fetched", ""), p.get("status", "")])
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(f"trends: {ok} refreshed, {blocked} rate limited, {failed} errors, {len(pairs)} pairs")

    try:
        from .push import LEADS_SHEET, Sheets
        Sheets().replace_tab(LEADS_SHEET, "Trends", rows, raw=True)
    except Exception as e:  # noqa: BLE001
        print(f"trends: sheet push failed: {e}")
    # healthy if at least something refreshed, or nothing was due
    return 0 if ok or not pairs else 1


if __name__ == "__main__":
    sys.exit(main())
