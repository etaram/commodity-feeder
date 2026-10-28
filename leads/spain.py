"""Spain: Plataforma de Contratación del Sector Público (PLACSP) ATOM syndication - every tender of the state,
regions and local entities. Open ('PUB') notices are kept; awards ('ADJ', 'RES') are counted for the awards layer."""
import datetime as dt
import html
import re

from .common import cache_empty, clean, log, rolling, session, today
from .sectors import from_cpv, classify
from .taxonomy import match_cpv

START = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
TYPE = {"1": "goods", "2": "services", "3": "works", "21": "goods", "31": "works"}


def _g(x, tag):
    m = re.search(r"<%s[^>]*>(.*?)</%s>" % (tag, tag), x, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def fetch():
    s, t = session(), today()
    cut = str(t - dt.timedelta(days=10 if cache_empty("spain") else 2))
    url, pages, new, awards = START, 0, [], 0
    while url and pages < 120:
        r = s.get(url, timeout=120); pages += 1
        if r.status_code != 200:
            log.warning("PLACSP %s", r.status_code); break
        txt = r.text
        entries = re.findall(r"<entry>(.*?)</entry>", txt, re.S)
        oldest = "9999"
        for x in entries:
            upd = _g(x, "updated")[:10]; oldest = min(oldest, upd or oldest)
            st = _g(x, "cbc-place-ext:ContractFolderStatusCode")
            if st in ("ADJ", "RES"):
                awards += 1; continue
            if st not in ("PUB", "PRE"):
                continue
            end = _g(x, "cbc:EndDate")[:10]
            if end and end < str(t):
                continue
            cpv = re.findall(r"<cbc:ItemClassificationCode[^>]*>(\d{8})</cbc:ItemClassificationCode>", x)
            title = clean(_g(x, "title"))
            gid, depth = match_cpv(cpv[:1])
            amt = _g(x, "cbc:EstimatedOverallContractAmount") or _g(x, "cbc:TotalAmount")
            buyer = re.search(r"<cac:PartyName>\s*<cbc:Name>(.*?)</cbc:Name>", x, re.S)
            link = re.search(r'<link[^>]*href="([^"]+)"', x)
            new.append({
                "id": "ES-" + _g(x, "id").rsplit("/", 1)[-1], "source": "PLACSP (Spain)", "group": gid or "",
                "match": depth if gid else "", "sector": from_cpv(cpv[:1]) or classify(title)[0],
                "nature": TYPE.get(_g(x, "cbc:TypeCode"), ""), "cpv": " ".join(dict.fromkeys(cpv[:6])),
                "classification": " ".join(dict.fromkeys(cpv[:6])), "country": "ESP",
                "buyer": clean(html.unescape(buyer.group(1)) if buyer else "", 120), "title": title[:300],
                "notice_type": "prior information" if st == "PRE" else "open call", "stage": "planned" if st == "PRE" else "tender",
                "access": "GPA/EU open", "published": upd, "deadline": end,
                "value": float(amt) if re.match(r"^[\d.]+$", amt or "") else "", "currency": "EUR" if amt else "",
                "link": html.unescape(link.group(1)) if link else "", "contact": "", "lang": "es",
            })
        if oldest < cut:
            break
        nxt = re.search(r'<link href="([^"]+)" rel="next"', txt)
        url = nxt.group(1) if nxt else None
    rows, _ = rolling("spain", new)
    log.info("PLACSP pages %d, new %d, open %d, award entries %d", pages, len(new), len(rows), awards)
    return rows, {"new": len(new), "pages": pages, "awards_seen": awards}
