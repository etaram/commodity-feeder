"""India - active tenders of the central and state e-procurement portals (NIC GePNIC software, the same public pages
anyone sees under 'Tenders by Organisation'). For each portal: list organisations with active tenders, then read each
organisation's tender table (published, closing date, title, reference, organisation chain). No login, no captcha.
Most Indian tenders are domestic or carry a Make in India preference; foreign suppliers usually need a local partner
or a 'global tender' notice, so the access field says to check before bidding. Rolling store."""
import datetime as dt
import html
import re
import time
from urllib.parse import urljoin

from .common import clean, log, polite, rolling, session, today
from .sectors import classify

PORTALS = [
    ("Central (CPPP)", "https://eprocure.gov.in/eprocure/app"),
    ("Central PSUs", "https://etenders.gov.in/eprocure/app"),
    ("Defence", "https://defproc.gov.in/nicgep/app"),
    ("Maharashtra", "https://mahatenders.gov.in/nicgep/app"),
    ("Tamil Nadu", "https://tntenders.gov.in/nicgep/app"),
    ("Kerala", "https://etenders.kerala.gov.in/nicgep/app"),
    ("Uttar Pradesh", "https://etender.up.nic.in/nicgep/app"),
    ("Haryana", "https://haryanaeprocurement.gov.in/nicgep/app"),
    ("Gujarat", "https://tender.nprocure.com"),
    ("Karnataka", "https://kppp.karnataka.gov.in"),
]
ORG_ROW = re.compile(r'<tr class="(?:even|odd)" id="informal_\d+">(.*?)</tr>', re.S)
BUDGET = 900  # seconds for the whole module


def _dt(txt):
    m = re.search(r"(\d{1,2}-[A-Z][a-z]{2}-\d{4})", txt)
    return dt.datetime.strptime(m.group(1), "%d-%b-%Y").date().isoformat() if m else ""


def _portal(s, name, base, t_end, today_s):
    root = base.rsplit("/", 1)[0] + "/"
    r = s.get(base + "?page=FrontEndTendersByOrganisation&service=page", timeout=60)
    r.raise_for_status()
    orgs = []
    for body in ORG_ROW.findall(r.text):
        a = re.search(r'href="([^"]+)"[^>]*>\s*(\d+)\s*<', body)
        nm = re.search(r"<td[^>]*>\s*([^<]{3,}?)\s*</td>\s*<td[^>]*>\s*<a", body)
        if a and nm and int(a.group(2)) > 0:
            orgs.append((clean(html.unescape(nm.group(1))), urljoin(root, html.unescape(a.group(1)))))
    log.info("India %s: %d organisations with active tenders", name, len(orgs))
    out = []
    for org, url in orgs:
        if time.time() > t_end:
            log.warning("India %s: time budget reached", name); break
        try:
            rr = s.get(url, timeout=60)
            rr.raise_for_status()
        except Exception as e:  # noqa: BLE001
            log.warning("India %s org %s: %s", name, org[:40], str(e)[:80]); continue
        pages = 0
        while True:
            for body in re.findall(r'<tr class="(?:even|odd)" id="informal_\d+">(.*?)</tr>', rr.text, re.S):
                tds = re.findall(r"<td[^>]*>(.*?)</td>", re.sub(r"<!--.*?-->", "", body, flags=re.S), re.S)
                if len(tds) < 6:
                    continue
                pub, close = _dt(tds[1]), _dt(tds[2])
                if close and close < today_s:
                    continue
                a = re.search(r">\s*\[([^\]]*)\]\s*</a>(.*)", tds[4], re.S)
                title = clean(html.unescape(a.group(1))) if a else clean(html.unescape(re.sub(r"<[^>]+>", " ", tds[4])))
                refs = re.findall(r"\[([^\]]+)\]", a.group(2)) if a else []
                tid = refs[-1] if refs else ""
                if not title or not tid:
                    continue
                chain = [clean(html.unescape(x)) for x in re.sub(r"<[^>]+>", "", tds[5]).split("||") if clean(x)]
                sector, method = classify(title)
                out.append({
                    "id": "IN-" + re.sub(r"\W", "", name)[:4].upper() + "-" + tid, "source": f"India e-procurement ({name})", "group": "",
                    "sector": sector, "nature": "", "cpv": "", "classification": method, "country": "IND",
                    "buyer": " - ".join(chain[:2]) or org, "title": (title + (f" [{tid}]" if tid not in title else ""))[:300],
                    "notice_type": "Tender", "stage": "tender",
                    "access": "Indian public tender: check whether it is a global tender or allows foreign bidders (Make in India preference and local registration usually apply)",
                    "published": pub or today_s, "deadline": close, "value": "", "currency": "",
                    "link": base + "?page=FrontEndLatestActiveTenders&service=page", "contact": f"Tender ID {tid}; search it on {root}", "lang": "",
                })
            nxt = re.search(r'id="(?:linkFwd|loopForward)[^"]*"[^>]*href="([^"]+)"|href="([^"]+)"[^>]*id="(?:linkFwd|loopForward)', rr.text)
            if not nxt or pages >= 40 or time.time() > t_end:
                break
            pages += 1
            rr = s.get(urljoin(root, html.unescape(nxt.group(1) or nxt.group(2))), timeout=60)
            polite(0.8)
        polite(0.8)
    return out


def fetch():
    s, t = session(), today()
    t_end = time.time() + BUDGET
    new = []
    for name, base in PORTALS:
        if time.time() > t_end:
            break
        try:
            rows = _portal(s, name, base, min(t_end, time.time() + 240), str(t))
            log.info("India %s: %d open tenders", name, len(rows)); new += rows
        except Exception as e:  # noqa: BLE001
            log.warning("India portal %s failed: %s", name, str(e)[:120])
    rows, _ = rolling("india", new, max_age_days=60)
    log.info("India new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
