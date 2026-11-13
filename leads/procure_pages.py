"""Corporate procurement pages (owner, 13 Nov 2026: not only government and international buyers, also companies of
medium size and up). Many companies publish their own requests for quotation / tenders on a 'Tenders', 'Procurement'
or 'Suppliers' page. For a company whose site we already read (site.jsonl, verdict ok), this module:

  1. fetches the home page (robots.txt respected) and keeps same-site links whose address or anchor text names a
     procurement page in any of 12 languages (careers / jobs pages are excluded);
  2. reads up to 2 such pages and extracts notice-like blocks (table rows, list items, cards) that carry a title, a
     closing / deadline wording and a date between today and 400 days ahead;
  3. drops blocks that say awarded, cancelled, closed or results.

Only a block with a FUTURE date next to a deadline word counts as an open request; the rest is kept as 'page found'
evidence only. Nothing here sends anything or signs in."""
import datetime as dt
import html as H
import re
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from . import company_check as cc

PROC = re.compile(r"tender|rfq|rfp|rfi\b|procure|purchas|sourcing|supplier|vendor|bid(s|ding)?\b|eoi\b|expression[- ]of[- ]interest|"
                  r"licitac|concurso|compras|proveedor|fornecedor|appels?[- ]d[- ]offres?|achats|fournisseur|ausschreibung|vergabe|"
                  r"einkauf|lieferant|gare\b|bandi|appalti|fornitor|aanbested|inkoop|przetarg|zam[oó]wien|ihale|tedarik|"
                  r"مناقص|مشتريات|موردين|מכרז|רכש|ספקים|招标|采购|供应商|入札|調達|조달|입찰|tender[- ]notice", re.I)
NOT_PROC = re.compile(r"career|jobs?\b|vacanc|recruit|empleo|emploi|karriere|lavora|vagas|wp-login|/login|account|cart|news-?letter", re.I)
DEADLINE = re.compile(r"clos(ing|es?|ure)|deadline|due\b|submi(t|ssion)|last date|valid until|ends?\b|opening date|bid date|"
                      r"cierre|fecha l[ií]mite|vencimiento|apertura|prazo|encerramento|date limite|cl[oô]ture|remise|abgabe|frist|"
                      r"einreichung|scadenza|termine|sluiting|termin|son teslim|موعد|آخر|תאריך|הגשה|截止|开标|締切|入札日|마감", re.I)
DEAD_WORDS = re.compile(r"\b(award(ed)?|cancel+ed|cancel+ation|closed|results?|adjudica|attribu[ée]|vergeben|aggiudicat|"
                        r"encerrad|cerrad|expired|archive)\b|ملغ|בוטל|已结束|中标结果", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE_RX = [
    (re.compile(r"\b(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d\d)\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(20\d\d)\b", re.I), "d_mon_y"),
    (re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I), "mon_d_y"),
    (re.compile(r"(20\d\d)年(\d{1,2})月(\d{1,2})日"), "ymd"),
]
BLOCK = re.compile(r"<(tr|li|article)\b[^>]*>(.*?)</\1>|<div\b[^>]*class=[\"'][^\"']*(?:tender|bid|rfq|card|item|notice|row)[^\"']*[\"'][^>]*>(.*?)</div>", re.I | re.S)
A_RX = re.compile(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)


def dates_in(text):
    out = []
    for rx, kind in DATE_RX:
        for m in rx.finditer(text):
            g = m.groups()
            try:
                if kind == "ymd":
                    d = dt.date(int(g[0]), int(g[1]), int(g[2]))
                elif kind == "dmy":
                    d = dt.date(int(g[2]), int(g[1]), int(g[0]))           # day first (most of the world)
                elif kind == "d_mon_y":
                    d = dt.date(int(g[2]), MONTHS[g[1][:3].lower()], int(g[0]))
                else:
                    d = dt.date(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1]))
            except (ValueError, KeyError):
                continue
            out.append(d)
    return out


def procure_links(base, page):
    host = cc.site_domain(base)
    out = []
    for m in A_RX.finditer(page):
        u = urljoin(base, m.group(1).strip())
        txt = re.sub(r"<[^>]+>", " ", m.group(2))
        if not u.startswith("http") or cc.site_domain(u) != host or u.rstrip("/") == base.rstrip("/"):
            continue
        hay = urlsplit(u).path + " " + txt
        if PROC.search(hay) and not NOT_PROC.search(hay) and u not in out:
            out.append(u)
    # pages that say tenders / rfq first, then procurement, then supplier registration pages
    rank = lambda u: (0 if re.search(r"tender|rfq|rfp|licitac|appel|ausschreib|gare|ihale|入札|招标|مناقص|מכרז", u, re.I) else  # noqa: E731
                      1 if re.search(r"procure|purchas|compras|achat|einkauf", u, re.I) else 2, len(u))
    return sorted(out, key=rank)


def notices(url, page, today, horizon=400):
    """Open requests on one page: [{title, deadline, link}] with a deadline word and a date in [today, today+horizon]."""
    out, seen = [], set()
    for m in BLOCK.finditer(page):
        inner = m.group(2) or m.group(3) or ""
        txt = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        if not (25 <= len(txt) <= 900) or DEAD_WORDS.search(txt) or not DEADLINE.search(txt):
            continue
        fut = [d for d in dates_in(txt) if today <= d <= today + dt.timedelta(days=horizon)]
        if not fut:
            continue
        a = max(A_RX.findall(inner), key=lambda x: len(re.sub(r"<[^>]+>", "", x[1]).strip()), default=None)
        title = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", a[1]))).strip() if a else ""
        if len(title) < 12:
            title = re.split(r"(?<=[.;:])\s|\s{2,}", txt)[0][:200]
        if len(title) < 12 or title.lower() in seen:
            continue
        seen.add(title.lower())
        out.append({"title": title[:300], "deadline": str(max(fut)), "link": urljoin(url, a[0]) if a else url,
                    "text": txt[:400]})
    return out


def scan(website, today):
    """{procurement_pages: [...], notices: [...], why} for one company site."""
    s = cc._session()
    first, code = cc._get(s, website if website.startswith("http") else "http://" + website)
    if not first:
        return {"procurement_pages": [], "notices": [], "why": f"unreachable ({code})"}
    final, home = first
    base = "{0.scheme}://{0.netloc}/".format(urlsplit(final))
    rp = RobotFileParser()
    rr, _ = cc._get(s, urljoin(base, "robots.txt"))
    rp.parse(rr[1].splitlines() if rr else [])
    pages = [u for u in procure_links(base, home) if rp.can_fetch(cc.UA, u)][:2]
    found = []
    for u in pages:
        got, _ = cc._get(s, u)
        if got:
            found += [dict(n, page=got[0]) for n in notices(got[0], got[1], today)]
    return {"procurement_pages": pages, "notices": found[:40], "why": "" if pages else "no procurement page linked from home"}
