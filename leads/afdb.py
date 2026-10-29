"""African Development Bank procurement notices from its official RSS feeds (afdb.org/en/rss-feeds):
project procurement notices (procurement.xml) and the Bank's own corporate solicitations.

Notices without a stated deadline are kept for 60 days after publication; General Procurement Notices are planned
tenders. Rolling store, so notices stay until they close."""
import datetime as dt
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .common import clean, log, polite, rolling, session, today
from .regions import iso3
from .sectors import classify

FEEDS = {
    "project": "https://www.afdb.org/en/projects-and-operations/procurement.xml",
    "corporate": "https://www.afdb.org/en/about-us/corporate-procurement/procurement-notices/current-solicitations.xml",
}
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre"
FR = {"janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8, "septembre": 9,
      "octobre": 10, "novembre": 11, "décembre": 12}


def _deadline(text):
    """Latest date mentioned next to a deadline word, e.g. 'submitted by 15 December 2026', 'au plus tard le 3 mars 2026'."""
    best = None
    for m in re.finditer(rf"(deadline|closing|submi\w+|au plus tard|date limite|before|no later than)[^.]{{0,80}}?(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS}),?\s+(20\d\d)", text, re.I):
        mon = m.group(3).lower()
        try:
            mo = FR.get(mon) or dt.datetime.strptime(mon[:3], "%b").month
            d = dt.date(int(m.group(4)), mo, int(m.group(2)))
        except ValueError:
            continue
        best = max(best, d) if best else d
    return best


FR_NAMES = {"guinée-bissau": "GNB", "guinée bissau": "GNB", "guinée": "GIN", "tunisie": "TUN", "comores": "COM", "maroc": "MAR",
            "cameroun": "CMR", "égypte": "EGY", "egypte": "EGY", "algérie": "DZA", "mauritanie": "MRT", "tchad": "TCD",
            "bénin": "BEN", "benin": "BEN", "rdc": "COD", "république démocratique du congo": "COD", "congo": "COG",
            "gabon": "GAB", "guinée équatoriale": "GNQ", "madagascar": "MDG", "maurice": "MUS", "libye": "LBY",
            "centrafrique": "CAF", "république centrafricaine": "CAF", "cap-vert": "CPV", "cabo verde": "CPV",
            "éthiopie": "ETH", "ouganda": "UGA", "tanzanie": "TZA", "zambie": "ZMB", "namibie": "NAM", "soudan": "SDN",
            "somalie": "SOM", "érythrée": "ERI", "sierra leone": "SLE", "gambie": "GMB", "nigéria": "NGA", "afrique du sud": "ZAF"}


def _country(title):
    for part in re.split(r"\s[-–—:]\s|\s*\|\s*|,\s*", title):
        p = part.strip()
        if len(p) <= 4:  # AMI, AAO, GPN, EOI ... are notice types, not countries
            continue
        c = FR_NAMES.get(p.lower()) or iso3(p)
        if c:
            return c
    m = re.search(r"\b(Multinational|Regional)\b", title, re.I)
    return "MULTI" if m else ""


def fetch():
    s, t, new = session(), today(), []
    for kind, url in FEEDS.items():
        try:
            r = s.get(url, timeout=60)
            root = ET.fromstring(r.content)
        except Exception as e:  # noqa: BLE001
            log.warning("AfDB %s: %s", kind, str(e)[:120]); continue
        items = root.findall(".//item")
        for it in items:
            title = clean(html.unescape(it.findtext("title") or ""))
            link = (it.findtext("link") or "").strip()
            desc = clean(html.unescape(re.sub(r"<[^>]+>", " ", it.findtext("description") or "")))
            try:
                pub = parsedate_to_datetime(it.findtext("pubDate")).date()
            except Exception:  # noqa: BLE001
                pub = None
            dl = _deadline(f"{title} {desc}")
            if dl and dl < t:
                continue
            if not dl and pub and pub < t - dt.timedelta(days=60):
                continue
            gpn = re.search(r"general procurement notice|avis général|^(GPN|AGPM|PPM)\b", title, re.I)
            sector, method = classify(f"{title} | {desc[:400]}")
            new.append({
                "id": "AfDB-" + (link.rstrip("/").rsplit("/", 1)[-1] or title)[:90], "source": "AfDB", "group": "",
                "sector": sector, "nature": "", "cpv": "", "classification": method,
                "country": _country(title) if kind == "project" else "CIV",
                "buyer": "AfDB-financed project" if kind == "project" else "African Development Bank (corporate)",
                "title": title[:300], "notice_type": "General Procurement Notice" if gpn else ("Corporate solicitation" if kind == "corporate" else "Procurement notice"),
                "stage": "planned" if gpn else "tender", "access": "International (AfDB rules, member countries)",
                "published": str(pub or ""), "deadline": str(dl or ""), "value": "", "currency": "", "link": link,
                "contact": "", "lang": "fr" if re.search(r"\b(avis|appel|projet|fourniture)\b", title, re.I) else "",
            })
        log.info("AfDB %s feed: %d items", kind, len(items))
        polite(2)
    rows, _ = rolling("afdb", new)
    log.info("AfDB new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
