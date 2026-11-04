"""World briefing feed: the news, geopolitical and expert context behind the deals (BRAIN.md).

Collects the last 48 hours from feeds, without AI: Google News RSS topic queries shipped with the code (trade and
sanctions, shipping, commodities, regional infrastructure), plus whatever the owner adds in the sheet tab
'Briefing Sources' (name, url, kind, topic, region): any RSS or Atom feed (news site, podcast show notes,
Substack or other newsletter, an expert's blog). YouTube channels are read through their RSS feed as well
(https://www.youtube.com/feeds/videos.xml?channel_id=...), titles and descriptions only.
Each item is tagged with the countries and commodity groups it mentions and a signal type (project, contract,
policy, price, risk, finance). "News leads" are items that name a company and a build/expand/award verb: a buyer
or project the tender feeds do not show yet. The daily brief itself (one Haiku call, cached per day) is made in the
web app when someone opens it: dealdesk/app/api/panel/brief.
Outputs: data/leads/briefing_items.csv, data/leads/news_leads.csv.   Run inside leads.run: python -m leads.briefing
"""
import csv
import datetime as dt
import email.utils
import html
import re
import time
import xml.etree.ElementTree as ET

from .common import LEADS, log, session, today
from .regions import iso3, region
from .taxonomy import group_of_text

GNEWS = "https://news.google.com/rss/search"
# shipped topic queries (Google News RSS is a public feed of headlines and links, credited to each publisher)
TOPICS = [
    ("trade policy", "global", '(tariff OR sanctions OR "export ban" OR "import ban" OR "trade deal" OR "free trade agreement") when:2d'),
    ("shipping", "global", '("Red Sea" OR Suez OR "container rates" OR "freight rates" OR "port congestion" OR "Baltic Dry") when:2d'),
    ("commodities", "global", '("wheat prices" OR "urea prices" OR "fertilizer prices" OR "steel prices" OR "copper prices" OR "crude prices" OR OPEC OR "sugar prices" OR "palm oil prices") when:2d'),
    ("geopolitics", "global", '(ceasefire OR "arms deal" OR "defense contract" OR coup OR "election results" OR "debt restructuring" OR IMF) (Africa OR "Middle East" OR Asia) when:2d'),
    ("infrastructure", "Sub-Saharan Africa", '(Africa) ("power plant" OR transmission OR railway OR port OR refinery OR "fertilizer plant" OR desalination OR "water project" OR "World Bank" OR "African Development Bank") when:2d'),
    ("infrastructure", "Middle East & North Africa", '(Saudi OR UAE OR Egypt OR Morocco OR Iraq OR Oman OR Qatar) ("awarded" OR "contract" OR "power plant" OR pipeline OR "water project" OR "signs") when:2d'),
    ("infrastructure", "South Asia", '(India OR Bangladesh OR "Sri Lanka" OR Pakistan OR Nepal) ("tender" OR "awarded" OR "power project" OR "railway" OR "port" OR "refinery") when:2d'),
    ("infrastructure", "Southeast Asia", '(Vietnam OR Indonesia OR Philippines OR Malaysia OR Thailand) ("awarded" OR "contract" OR "power plant" OR "port" OR "railway" OR "LNG") when:2d'),
    ("infrastructure", "CIS & Central Asia", '(Kazakhstan OR Uzbekistan OR Azerbaijan OR Georgia OR Kyrgyzstan) ("contract" OR "power plant" OR "railway" OR "mining" OR "fertilizer") when:2d'),
    ("infrastructure", "Latin America", '(Brazil OR Colombia OR Peru OR Chile OR Mexico OR Argentina) ("awarded" OR "licitación" OR "power plant" OR "port" OR "mining" OR "railway") when:2d'),
    ("israel trade", "Israel", '(Israel) (exports OR imports OR "trade agreement" OR "free trade" OR Abraham OR "defense exports" OR desalination) when:2d'),
    ("china outbound", "East Asia", '("Chinese company" OR "China" OR "Belt and Road") (Africa OR "Middle East" OR "Central Asia" OR "Latin America") ("contract" OR "signs" OR "build" OR "invest") when:2d'),
]
SIGNAL = [("contract", r"\b(awarded|wins? (the )?contract|signs?|signed|secures?|agreement)\b"),
          ("project", r"\b(to build|will build|plans? to|breaks ground|construction of|expansion|new plant|MW\b|GW\b|refinery|pipeline|railway|port)\b"),
          ("policy", r"\b(tariff|sanction|ban|quota|subsid|regulat|law|decree|policy|licen[cs]e)\b"),
          ("price", r"\b(prices?|surge|slump|rally|falls?|rises?|record high|record low|\$\d)"),
          ("finance", r"\b(World Bank|IMF|AfDB|loan|financing|bond|fund|investment|invests?)\b"),
          ("risk", r"\b(strike|protest|coup|attack|flood|drought|outage|default|crisis|war|ceasefire)\b")]
LEAD_RX = re.compile(r"\b([A-Z][\w&.'-]+(?: [A-Z][\w&.'-]+){0,4}) (?:to build|will build|plans? to build|breaks ground on|awarded|wins|signs|to invest|invests|to expand|to set up|to construct|commissions)\b")
COUNTRIES = {}  # name -> iso3, lazily from pycountry


def _countries():
    if COUNTRIES:
        return COUNTRIES
    try:
        import pycountry
        for c in pycountry.countries:
            for n in {c.name, getattr(c, "common_name", c.name), getattr(c, "official_name", c.name)}:
                if n and len(n) > 3:
                    COUNTRIES[n] = c.alpha_3
    except Exception:  # noqa: BLE001
        pass
    COUNTRIES.update({"UAE": "ARE", "Saudi": "SAU", "Kenya": "KEN", "Ethiopia": "ETH", "Vietnam": "VNM", "Iran": "IRN", "Russia": "RUS",
                      "Turkey": "TUR", "Türkiye": "TUR", "Tanzania": "TZA", "Ivory Coast": "CIV", "DRC": "COD", "Congo": "COD", "Egypt": "EGY"})
    return COUNTRIES


def mentions(text):
    out = []
    for n, c in _countries().items():
        if re.search(r"\b" + re.escape(n) + r"\b", text):
            if c not in out:
                out.append(c)
    return out[:4]


def _feed(s, url, params=None):
    try:
        r = s.get(url, params=params, timeout=40)
        if r.status_code != 200:
            log.warning("feed %s: HTTP %s", url[:60], r.status_code); return []
        root = ET.fromstring(r.content)
    except Exception as e:  # noqa: BLE001
        log.warning("feed %s: %s", url[:60], type(e).__name__); return []
    ns = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/"}
    items = []
    for it in root.iter("item"):  # RSS 2.0
        src = it.find("source")
        items.append({"title": it.findtext("title") or "", "url": it.findtext("link") or "", "date": it.findtext("pubDate") or "",
                      "summary": it.findtext("description") or "", "source": (src.text if src is not None else "") or ""})
    for it in root.iter("{http://www.w3.org/2005/Atom}entry"):  # Atom (YouTube, many blogs)
        link = it.find("a:link", ns)
        items.append({"title": it.findtext("a:title", default="", namespaces=ns), "url": (link.get("href") if link is not None else "") or "",
                      "date": it.findtext("a:published", default="", namespaces=ns) or it.findtext("a:updated", default="", namespaces=ns),
                      "summary": it.findtext("a:summary", default="", namespaces=ns) or it.findtext("m:group/m:description", default="", namespaces=ns), "source": ""})
    return items


def _telegram(s, channel):
    """Public Telegram channel preview (t.me/s/<channel>): the last messages as items. No account, no bot token."""
    try:
        r = s.get(f"https://t.me/s/{channel}", timeout=30)
        if r.status_code != 200:
            log.warning("telegram %s: HTTP %s", channel, r.status_code); return []
        page = r.text
    except Exception as e:  # noqa: BLE001
        log.warning("telegram %s: %s", channel, type(e).__name__); return []
    out = []
    for m in re.finditer(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>.*?<a class="tgme_widget_message_date" href="([^"]+)"[^>]*><time datetime="([^"]+)"', page, re.S):
        text = html.unescape(re.sub(r"<br\s*/?>", " ", m.group(1)))
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            out.append({"title": text[:160], "url": m.group(2), "date": m.group(3), "summary": text[160:460], "source": f"t.me/{channel}"})
    return out[-30:]


def _when(v):
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v or ""):
        return dt.date.fromisoformat(v)
    try:
        return email.utils.parsedate_to_datetime(v).date()
    except (TypeError, ValueError):
        try:
            return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def owner_sources():
    """Sheet tab 'Briefing Sources' (name, url, kind, topic, region); missing or unreachable -> none."""
    try:
        from .push import LEADS_SHEET, Sheets
        rows = Sheets().values(LEADS_SHEET, "'Briefing Sources'!A2:E200")
        return [{"name": r[0], "url": r[1], "kind": (r[2] if len(r) > 2 else "rss") or "rss", "topic": (r[3] if len(r) > 3 else "") or "expert",
                 "region": (r[4] if len(r) > 4 else "") or "global"} for r in rows if len(r) > 1 and (r[1].startswith("http") or (len(r) > 2 and r[2].lower().startswith("company")))]
    except Exception as e:  # noqa: BLE001
        log.warning("briefing sources tab: %s", type(e).__name__); return []


def build():
    s, t = session(), today()
    since = t - dt.timedelta(days=2)
    items, seen = [], set()

    def add(it, topic, regn, source):
        d = _when(it["date"])
        if d and d < since:
            return
        title = html.unescape(re.sub(r"<[^>]+>", "", it["title"])).strip()
        if source == "Google News" and " - " in title:
            title, _, pub = title.rpartition(" - ")
            source = it.get("source") or pub
        k = re.sub(r"\W+", " ", title.lower())[:70]
        if not title or k in seen:
            return
        seen.add(k)
        summ = html.unescape(re.sub(r"<[^>]+>", " ", it.get("summary") or "")).strip()[:300]
        text = f"{title} {summ}"
        sig = next((n for n, rx in SIGNAL if re.search(rx, text, re.I)), "")
        cs = mentions(text)
        m = LEAD_RX.search(title)
        if m and (m.group(1) in _countries() or re.fullmatch(r"(The )?(Contractor|Government|Ministry|Company|Firm|Consortium|Group|State|President|Minister|Officials?|Report|Why|How|What|When)", m.group(1), re.I)):
            m = None
        items.append({"date": str(d or t), "topic": topic, "region": regn or (region(cs[0]) if cs else ""), "title": title[:200], "source": (it.get("source") or source)[:60],
                      "url": it["url"], "countries": " ".join(cs), "group": group_of_text(text) or "", "signal": sig,
                      "lead_company": (m.group(1) if m and len(m.group(1)) > 3 else "")[:80], "summary": summ})

    for topic, regn, q in TOPICS:
        for it in _feed(s, GNEWS, {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}):
            add(it, topic, regn, "Google News")
        time.sleep(1)
    for src in owner_sources():
        kind = src["kind"].lower()
        if kind.startswith("reddit"):  # url column: subreddit name or its URL; Reddit's public RSS, relayed if the runner is refused
            sub_ = re.sub(r"^.*?/r/|/.*$", "", src["url"]).strip("/") or src["name"]
            for it in _feed(s, f"https://www.reddit.com/r/{sub_}/new/.rss"):
                add(it, src["topic"] or "community", src["region"], f"r/{sub_}")
        elif kind.startswith("telegram"):  # url column: public channel name or t.me link; the public preview page, no account
            ch = re.sub(r"^.*?t\.me/(s/)?|/.*$", "", src["url"]).strip("/") or src["name"]
            for it in _telegram(s, ch):
                add(it, src["topic"] or "community", src["region"], f"t.me/{ch}")
        elif kind.startswith("company"):  # a company to watch: its name in the url column is enough
            q = src["url"] if not src["url"].startswith("http") else src["name"]
            for it in _feed(s, GNEWS, {"q": f'"{q}" when:7d', "hl": "en-US", "gl": "US", "ceid": "US:en"}):
                add(it, "company watch", src["region"], "Google News")
        else:
            for it in _feed(s, src["url"]):
                add(it, src["topic"], src["region"], src["name"])
        time.sleep(1)
    sp = LEADS / "social.csv"  # community signals collected by leads.social (same shape)
    if sp.exists():
        for it in csv.DictReader(open(sp, encoding="utf-8")):
            add({"title": it["title"], "url": it["url"], "date": it["date"], "summary": it.get("summary", ""), "source": it["source"]}, it["topic"], it.get("region", ""), it["source"])
    items.sort(key=lambda x: (x["date"], x["topic"]), reverse=True)
    cols = ["date", "topic", "region", "title", "source", "url", "countries", "group", "signal", "lead_company", "summary"]
    with open(LEADS / "briefing_items.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(items[:600])
    leads = [{"date": x["date"], "company": x["lead_company"], "country": x["countries"].split(" ")[0] if x["countries"] else "", "region": x["region"],
              "what": x["title"], "group": x["group"], "signal": x["signal"], "source": x["source"], "url": x["url"]}
             for x in items if x["lead_company"] and x["signal"] in ("project", "contract", "finance")]
    with open(LEADS / "news_leads.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "company", "country", "region", "what", "group", "signal", "source", "url"]); w.writeheader(); w.writerows(leads[:300])
    log.info("briefing: %d items, %d news leads", len(items), len(leads))
    return items, leads


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    it, ld = build()
    for x in ld[:8]:
        print(x["country"], "|", x["company"], "|", x["what"][:90])
