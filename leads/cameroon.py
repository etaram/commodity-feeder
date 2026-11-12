"""Cameroon: ARMP (Agence de Regulation des Marches Publics) public notices list (https://armp.cm/?page=N): calls for
tenders and expressions of interest of ministries, regions, councils and state companies - title, contracting
authority (PO/CA), region, amount, publication date, closing date. 10 per page, all notice types mixed, newest first;
communiques (COMM) and award decisions (DEC-ATTR) are skipped here.

Access (checked 2026-11-12): plain HTTP from the runner (method: http); robots.txt "User-agent: * Disallow:" (all
allowed); no terms-of-use page found. Polite: 2 s between pages, at most MAX_PAGES pages per run."""
import datetime as dt
import html
import re

from .common import clean, log, polite, quarantine_future, rolling, today
from .sectors import classify

BASE = "https://armp.cm/"
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
DAYS, MAX_PAGES = 7, 30
SKIP = {"COMM", "DEC-ATTR", "DEC-RES", "ADD"}
LI = re.compile(r'<li href="#" class="list-group-item.*?</li>', re.S)


def _field(li, label):
    m = re.search(r">\s*" + re.escape(label) + r"\s*:?\s*</div>\s*<div class=\"([^\"]*)\">\s*(.*?)\s*</div>", li, re.S)
    if not m or "d-none" in m.group(1):
        return ""
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))))


def _date(s):
    m = re.search(r"(\d\d)-(\d\d)-(\d{4})", s or "")
    d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""
    return "" if d.startswith("1970") else d


def parse(body, fetched):
    out = []
    for li in LI.findall(body):
        m = re.search(r"details\?type_publication=([\w-]+)&(?:amp;)?id_publication=(\d+)", li)
        if not m or m.group(1) in SKIP:
            continue
        typ, pid = m.group(1), m.group(2)
        t = re.search(r'<strong title="([^"]*)"', li)
        title = clean(html.unescape(t.group(1))) if t else ""
        if not title:
            continue
        sector, how = classify(title)
        amount = re.sub(r"[^\d]", "", _field(li, "Amount"))
        region = _field(li, "Region")
        out.append({"id": f"CM-{typ}-{pid}", "source": "ARMP (Cameroon)", "group": "", "sector": sector, "nature": "", "cpv": "",
                    "classification": how, "country": "CMR", "buyer": _field(li, "PO/CA")[:120], "title": title[:300],
                    "notice_type": {"AMI": "Expression of interest (AMI)", "AO": "Call for tenders (AO)"}.get(typ, typ), "stage": "tender",
                    "access": "National (ARMP rules; international calls marked AOI)", "published": _date(_field(li, "Published on the")),
                    "deadline": _date(_field(li, "Closing date")), "value": float(amount) if amount else "", "currency": "XAF" if amount else "",
                    "link": f"https://armp.cm/details?type_publication={typ}&id_publication={pid}", "source_url": BASE, "fetched": fetched,
                    "contact": "", "lang": "fr", "region_local": region,
                    "gov_level": "national" if region.upper() in ("CENTRAL SERVICES", "SERVICES CENTRAUX", "") else "regional/local"})
    return out


def fetch():
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "en,fr;q=0.8"})
    t = today(); cut = str(t - dt.timedelta(days=DAYS)); new, seen_pub = [], []
    for page in range(1, MAX_PAGES + 1):
        r = s.get(BASE, params={"page": page} if page > 1 else None, timeout=60)
        if r.status_code != 200:
            log.warning("Cameroon page %d: HTTP %s", page, r.status_code); break
        r.encoding = "utf-8"
        rows = parse(r.text, str(t))
        pubs = [_date(x) for x in re.findall(r"Published on the :\s*</div>\s*<div class=\"d-table-cell\">\s*([\d-]+)", r.text)]
        seen_pub += pubs
        new += [x for x in rows if not x["deadline"] or x["deadline"] >= str(t)]
        if not pubs or min(pubs) < cut:
            break
        polite(2)
    new, q = quarantine_future(new, "cameroon")
    keep, _ = rolling("cameroon", new, max_age_days=60)
    log.info("Cameroon ARMP: %d open calls (%d pages), %d kept", len(new), page, len(keep))
    return keep, {"new": len(new), "pages": page}
