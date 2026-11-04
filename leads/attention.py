"""Attention signals without the Google Trends API (access not granted): two official, free sources.

1. Google Trends daily trending searches, published as an RSS feed per country (trends.google.com/trending/rss?geo=XX):
   what a country is searching today. Not keyword interest, but a live read of the national agenda; items that
   mention a commodity, an infrastructure word or a watched company are kept as signals.
2. Wikipedia pageviews (Wikimedia REST API, no key): daily views of the articles for the commodities, countries and
   companies the system tracks, with the change over 30 days. Attention to "Urea" or "Red Sea crisis" rising
   sharply is an early signal, and the series is complete and official.
Output: data/leads/attention.csv (kind, country, term, value, chg_30d_pct, note, url). Run inside leads.run.
"""
import csv
import datetime as dt
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET

from .common import LEADS, log, session, today

TRENDS_RSS = "https://trends.google.com/trending/rss"
WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/daily/{start}/{end}"
TOPIC_RX = re.compile(r"\b(tender|procurement|power|electric|fuel|diesel|petrol|wheat|maize|rice|sugar|fertiliz|urea|cement|steel|port|railway|pipeline|"
                      r"refinery|solar|dam|water|drought|flood|strike|sanction|tariff|export|import|shipping|mining|gold|copper|cobalt|lithium|oil|gas|lng)\b", re.I)
# Wikipedia articles watched: commodities and trade themes; the owner's companies come from the Briefing Sources tab (kind=company)
ARTICLES = ["Urea", "Wheat", "Maize", "Rice", "Sugar", "Palm_oil", "Sunflower_oil", "Fertilizer", "Steel", "Rebar", "Cement", "Copper", "Aluminium", "Cobalt",
            "Lithium", "Crude_oil", "Liquefied_natural_gas", "Diesel_fuel", "Solar_panel", "Transformer", "Desalination", "Red_Sea_crisis", "Suez_Canal",
            "Baltic_Dry_Index", "Tariff", "Economic_sanctions", "World_Bank", "African_Development_Bank", "Belt_and_Road_Initiative"]


def trending(s, iso2):
    try:
        r = s.get(TRENDS_RSS, params={"geo": iso2}, timeout=30)
        if r.status_code != 200:
            log.warning("trends rss %s: HTTP %s", iso2, r.status_code); return []
        root = ET.fromstring(r.content)
        log.info("trends rss %s: %d items", iso2, sum(1 for _ in root.iter("item")))
    except Exception as e:  # noqa: BLE001
        log.warning("trends rss %s: %s", iso2, type(e).__name__); return []
    out = []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        traffic = (it.findtext("ht:approx_traffic", default="", namespaces=ns) or "").strip()
        news = it.find("ht:news_item", ns)
        headline = (news.findtext("ht:news_item_title", default="", namespaces=ns) if news is not None else "") or ""
        url = (news.findtext("ht:news_item_url", default="", namespaces=ns) if news is not None else "") or ""
        if title:
            out.append({"term": title, "traffic": traffic, "headline": headline[:160], "url": url, "business": bool(TOPIC_RX.search(f"{title} {headline}"))})
    return out


def pageviews(s, title):
    end, start = today() - dt.timedelta(days=1), today() - dt.timedelta(days=61)
    try:
        r = s.get(WIKI.format(title=urllib.parse.quote(title), start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d")), timeout=30, headers={"User-Agent": "sinder-deal-desk/1.0 (research; contact via github etaram/commodity-feeder)"})
        if r.status_code != 200:
            return None
        items = r.json().get("items") or []
    except Exception as e:  # noqa: BLE001
        log.warning("wiki %s: %s", title, type(e).__name__); return None
    v = [x.get("views", 0) for x in items]
    if len(v) < 40:
        return None
    last, prev = sum(v[-30:]) / 30, sum(v[-60:-30]) / 30
    return {"views_30d_avg": round(last), "chg_30d_pct": round((last / prev - 1) * 100, 1) if prev else "", "peak_day": max(v[-30:])}


def _iso2(iso3):
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=iso3)
        return c.alpha_2 if c else ""
    except Exception:  # noqa: BLE001
        return ""


def build(countries=None):
    s, rows = session(), []
    for iso3 in (countries or ["ISR", "KEN", "NGA", "GHA", "ETH", "EGY", "MAR", "SAU", "ARE", "IND", "ZAF", "TZA", "UGA", "VNM", "PHL"])[:40]:
        iso2 = _iso2(iso3)
        if not iso2:
            continue
        for x in trending(s, iso2):
            if x["business"]:
                rows.append({"kind": "trending search", "country": iso3, "term": x["term"], "value": x["traffic"], "chg_30d_pct": "", "note": x["headline"], "url": x["url"]})
        time.sleep(1)
    for a in ARTICLES:
        pv = pageviews(s, a)
        if pv:
            rows.append({"kind": "wikipedia attention", "country": "", "term": a.replace("_", " "), "value": pv["views_30d_avg"], "chg_30d_pct": pv["chg_30d_pct"],
                         "note": f"peak day {pv['peak_day']}", "url": f"https://en.wikipedia.org/wiki/{a}"})
        time.sleep(0.3)
    with open(LEADS / "attention.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "country", "term", "value", "chg_30d_pct", "note", "url"]); w.writeheader(); w.writerows(rows)
    log.info("attention: %d rows (%d trending, %d wikipedia)", len(rows), sum(1 for r in rows if r["kind"] == "trending search"), sum(1 for r in rows if r["kind"] != "trending search"))
    return rows


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    for r in build(["KEN", "ISR", "SAU"])[:12]:
        print(r)
