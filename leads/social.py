"""Community signals: Reddit, Hacker News and public Telegram channels, into the same briefing feed.

- Reddit: public listing JSON of chosen subreddits (new posts, last 48 h, a minimum score), read politely with a
  descriptive user agent; Reddit refuses many cloud addresses (403), so the regional relay is the fallback. The
  official API (free, needs an app registered by the owner) can replace this later: REDDIT_CLIENT_ID/SECRET in Config.
- Hacker News: Algolia search API (free, no key) for trade and infrastructure terms.
- Telegram: public channel preview pages (t.me/s/<channel>), for channels the owner lists in the sheet tab
  Briefing Sources with kind "telegram" (African and Gulf business outlets post there first).
Output: data/leads/social.csv in the briefing item shape; leads.briefing merges it. Run inside leads.run before briefing.
"""
import csv
import datetime as dt
import html
import re
import time

from .common import LEADS, log, session, today
from .regions import region

SUBS = [("supplychain", "logistics"), ("logistics", "logistics"), ("Commodities", "commodities"), ("energy", "energy"), ("geopolitics", "geopolitics"),
        ("africa", "Sub-Saharan Africa"), ("Kenya", "Sub-Saharan Africa"), ("Nigeria", "Sub-Saharan Africa"), ("Ethiopia", "Sub-Saharan Africa"),
        ("Ghana", "Sub-Saharan Africa"), ("southafrica", "Sub-Saharan Africa"), ("Egypt", "Middle East & North Africa"), ("saudiarabia", "Middle East & North Africa"),
        ("dubai", "Middle East & North Africa"), ("india", "South Asia"), ("Pakistan", "South Asia"), ("vietnam", "Southeast Asia"), ("Philippines", "Southeast Asia"),
        ("Israel", "Israel"), ("manufacturing", "industry"), ("procurement", "procurement"), ("mining", "mining"), ("solar", "energy")]
BIZ = re.compile(r"\b(tender|procurement|contract|awarded|power|electric|grid|outage|fuel|diesel|petrol|shortage|wheat|maize|rice|sugar|fertili[sz]|urea|cement|steel|"
                 r"port|railway|pipeline|refinery|solar|dam|desalin|water|drought|flood|strike|sanction|tariff|export|import|shipping|freight|container|mining|"
                 r"copper|cobalt|lithium|oil|gas|lng|loan|world bank|imf|investment|factory|plant|\$\d|million|billion)\b", re.I)
HN = "https://hn.algolia.com/api/v1/search"
HN_TERMS = ["supply chain", "tariff", "sanctions", "shipping", "Red Sea", "fertilizer", "commodity prices", "infrastructure Africa", "World Bank"]


_TOKEN = {}


def reddit_token(s):
    """Official Reddit API (free): app credentials REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET from the environment or the
    Supplier Universe sheet, tab Config. Without them the public listing is tried, which cloud addresses rarely get."""
    import os
    if "v" in _TOKEN:
        return _TOKEN["v"]
    cid, sec = os.environ.get("REDDIT_CLIENT_ID", ""), os.environ.get("REDDIT_CLIENT_SECRET", "")
    if not (cid and sec):
        try:
            from .push import UNIVERSE_SHEET, Sheets
            cfg = {r[0]: r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B12") if len(r) > 1}
            cid, sec = cfg.get("REDDIT_CLIENT_ID", cid), cfg.get("REDDIT_CLIENT_SECRET", sec)
        except Exception:  # noqa: BLE001
            pass
    tok = ""
    if cid and sec:
        try:
            r = s.post("https://www.reddit.com/api/v1/access_token", auth=(cid, sec), data={"grant_type": "client_credentials"},
                       headers={"User-Agent": UA_R}, timeout=30)
            tok = r.json().get("access_token", "") if r.status_code == 200 else ""
            if not tok:
                log.warning("reddit token: HTTP %s", r.status_code)
        except Exception as e:  # noqa: BLE001
            log.warning("reddit token: %s", type(e).__name__)
    _TOKEN["v"] = tok
    return tok


UA_R = "sinder-deal-desk/1.0 (business research feed; github etaram/commodity-feeder)"


def reddit(s, sub, regn, since):
    tok = reddit_token(s)
    url = f"https://oauth.reddit.com/r/{sub}/new" if tok else f"https://www.reddit.com/r/{sub}/new.json"
    try:
        r = s.get(url, params={"limit": 50}, timeout=30, headers={"User-Agent": UA_R, **({"Authorization": f"Bearer {tok}"} if tok else {})})
        if r.status_code != 200:
            log.warning("reddit r/%s: HTTP %s", sub, r.status_code); return []
        posts = (r.json().get("data") or {}).get("children") or []
    except Exception as e:  # noqa: BLE001
        log.warning("reddit r/%s: %s", sub, type(e).__name__); return []
    out = []
    for p in posts:
        d = p.get("data") or {}
        ts = dt.datetime.utcfromtimestamp(d.get("created_utc") or 0).date()
        if ts < since or (d.get("score") or 0) < 5 or d.get("over_18"):
            continue
        title = html.unescape(d.get("title") or "")
        if not BIZ.search(f"{title} {d.get('selftext') or ''}"):
            continue
        out.append({"date": str(ts), "topic": "reddit", "region": regn if regn in ("Sub-Saharan Africa", "Middle East & North Africa", "South Asia", "Southeast Asia", "Israel") else "global",
                    "title": title[:200], "source": f"r/{sub} ({d.get('score')} points)", "url": "https://www.reddit.com" + (d.get("permalink") or ""),
                    "summary": html.unescape((d.get("selftext") or "")[:300]).replace("\n", " ")})
    return out


def hackernews(s, since):
    out, seen = [], set()
    for term in HN_TERMS:
        try:
            r = s.get(HN, params={"query": term, "tags": "story", "numericFilters": f"created_at_i>{int(dt.datetime.combine(since, dt.time()).timestamp())},points>20", "hitsPerPage": 20}, timeout=30)
            hits = r.json().get("hits") or [] if r.status_code == 200 else []
        except Exception as e:  # noqa: BLE001
            log.warning("hn %s: %s", term, type(e).__name__); hits = []
        for h in hits:
            if h.get("objectID") in seen or term.lower() not in (h.get("title") or "").lower():
                continue  # relevance search returns loose matches: keep only titles that carry the term
            seen.add(h.get("objectID"))
            out.append({"date": (h.get("created_at") or "")[:10], "topic": "hacker news", "region": "global", "title": (h.get("title") or "")[:200],
                        "source": f"Hacker News ({h.get('points')} points)", "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}", "summary": ""})
        time.sleep(0.5)
    return out


def telegram(s, channel, regn, since):
    url = f"https://t.me/s/{channel.strip('@/ ')}"
    try:
        r = s.get(url, timeout=30)
        if r.status_code != 200:
            log.warning("telegram %s: HTTP %s", channel, r.status_code); return []
        page = r.text
    except Exception as e:  # noqa: BLE001
        log.warning("telegram %s: %s", channel, type(e).__name__); return []
    out = []
    for m in re.finditer(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>.*?<a class="tgme_widget_message_date" href="([^"]+)"[^>]*><time datetime="([^"]+)"', page, re.S):
        text = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip()
        d = m.group(3)[:10]
        if not text or d < str(since):
            continue
        out.append({"date": d, "topic": "telegram", "region": regn or "global", "title": text[:200], "source": f"t.me/{channel}", "url": m.group(2), "summary": text[200:500]})
    return out[-40:]


def owner_channels():
    try:
        from .push import LEADS_SHEET, Sheets
        rows = Sheets().values(LEADS_SHEET, "'Briefing Sources'!A2:E200")
        return [(r[1] if len(r) > 1 and r[1] and not r[1].startswith("http") else r[0], (r[4] if len(r) > 4 else "") or "")
                for r in rows if len(r) > 2 and str(r[2]).lower().startswith("telegram")]
    except Exception as e:  # noqa: BLE001
        log.warning("telegram channels tab: %s", type(e).__name__); return []


def build():
    s, since = session(), today() - dt.timedelta(days=2)
    rows = []
    for sub, regn in SUBS:
        rows += reddit(s, sub, regn, since)
        if not reddit_token(s) and not rows:
            log.warning("reddit: no app credentials and the public listing refused; skipping the rest"); break
        time.sleep(2)
    rows += hackernews(s, since)
    for ch, regn in owner_channels():
        rows += telegram(s, ch, regn, since)
        time.sleep(1)
    with open(LEADS / "social.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "topic", "region", "title", "source", "url", "summary"]); w.writeheader(); w.writerows(rows)
    log.info("social: %d items (%d reddit, %d hn, %d telegram)", len(rows), sum(1 for r in rows if r["topic"] == "reddit"), sum(1 for r in rows if r["topic"] == "hacker news"), sum(1 for r in rows if r["topic"] == "telegram"))
    return rows


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    for r in build()[:10]:
        print(r["date"], r["source"], "|", r["title"][:90])
