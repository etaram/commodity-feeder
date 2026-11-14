"""Directory sweep: the tender pages of ~400 cities, state-owned enterprises and national agencies from the owner's
'Global Open Procurement 500' list and its 1,500 master directory (data/leads/sources/directory500.csv, received 14 Nov 2026,
batch 2 ids prefixed B2-; every entry marked
'Not Reviewed' there, so each page is checked here). Entries whose host another collector already reads are skipped.

For each entry: fetch the listed page politely (robots.txt respected, CAPTCHA and bot walls are never passed: they are
reported as 'robots' / 'blocked'), find notice links whose text or row looks like a tender in any of the common
procurement languages, read a closing date from the row (day-first except in the US, Canada and the Philippines),
and keep only notices with a closing date today or later. One level of 'tenders' sub-page is followed when the page
itself lists nothing. A per-entry status (counts only) is written to data/leads/directory500_status.csv, which is the
triage list for dedicated collectors.

Rows are generic page extractions: their buyer is the entity named in the directory and their link is the notice link
found on the page. Time-boxed; the stalest entries are read first so the whole list rotates over runs."""
import csv
import datetime as dt
import re
import time
from urllib.parse import urljoin, urlparse

from .common import LEADS, clean, log, rolling, today
from .il_web import fetch, soup
from .sectors import classify

LIST = LEADS / "sources" / "directory500.csv"
STATUS = LEADS / "directory500_status.csv"
BUDGET_S = 2100
TENDER = re.compile(
    r"\b(tenders?|RFPs?|RFQs?|RFIs?|IFBs?|ITBs?|EOIs?|solicitations?|invitations? (?:to|for) (?:bid|tender)s?|"
    r"requests? for (?:proposals?|quot\w+|qualifications|bids?|information|expressions? of interest)|expressions? of interest|"
    r"bid (?:no\.?|number|#)|procurement notice|appel(?:s)? d'offres?|avis d'appel|consultation|march[ée]s? public|"
    r"licitaci[oó]n|concurso|cotizaci[oó]n|licita[cç][aã]o|preg[aã]o|ausschreibung|vergabe|gara d'appalto|bando di gara|"
    r"aanbesteding|przetarg|zam[oó]wieni|ihale|ilan|tarjouskilpailu|upphandling|udbud|anbud|nab[ií]dk|ve[rř]ejn[aá] zak[aá]zk|"
    r"lelang|pengadaan|đấu thầu|ประกวด|入札|公告|招标|採購|입찰|مناقص|عطاء|מכרז)", re.I)
SKIP = re.compile(r"\b(jobs?|careers?|employment|vacanc|recruit|internship|awarded|award notice|results?|tabulation|closed|"
                  r"cancel+ed|archive|minutes|how to|guide|register|registration|login|sign in|faq|policy|news|press|"
                  r"résultats?|attribu|adjudicad|zuschlag|aggiudicaz|gunning|wynik|sonuç|תוצאות|זוכה)\b", re.I)
GENERIC = re.compile(r"^(click here|more|details|view|download|pdf|read more|learn more|here|link|voir|ver|mehr|lire la suite)$", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DUE = re.compile(r"due|clos|deadline|submi|last date|until|limite|date limite|cierre|vencimiento|encerramento|"
                 r"frist|ablauf|scadenza|sluiting|termin|son teklif|תאריך אחרון|הגשה|موعد|آخر|締切|마감|截止", re.I)
MONTH_FIRST = {"USA", "CAN", "PHL"}


def _dates(s, t, month_first):
    out = []
    for a, b, y in re.findall(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d\d|\d\d)(?!\d)", s):
        y = int(y) + (2000 if len(y) == 2 else 0)
        m, d = (int(a), int(b)) if month_first else (int(b), int(a))
        out.append((y, m, d))
    out += [(int(y), int(m), int(d)) for y, m, d in re.findall(r"(?<!\d)(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", s)]
    out += [(int(y), MONTHS[m[:3].lower()], int(d)) for m, d, y in
            re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d\d)\b", s, re.I)]
    out += [(int(y), MONTHS[m[:3].lower()], int(d)) for d, m, y in
            re.findall(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(20\d\d)\b", s, re.I)]
    res = []
    for y, m, d in out:
        try:
            x = dt.date(y, m, d)
        except ValueError:
            continue
        if t.year - 1 <= x.year <= t.year + 2:
            res.append(x)
    return res


def _deadline(ctx, t, mf):
    for m in DUE.finditer(ctx):
        ds = _dates(ctx[m.start(): m.start() + 100], t, mf)
        if ds:
            return ds[0]
    fut = [d for d in _dates(ctx, t, mf) if d >= t]
    return max(fut) if fut else None


def extract(page_url, text, t, mf):
    sp = soup(text)
    for x in sp(["script", "style", "noscript", "header", "footer", "nav"]):
        x.decompose()
    items, seen = [], set()
    for a in sp.find_all("a", href=True):
        at = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        box = a
        for _ in range(6):
            p = box.parent
            if p is None or p.name in ("body", "html", "main", "form") or len(p.get_text(" ", strip=True)) > 900:
                break
            box = p
            if p.name in ("tr", "li", "article"):
                break
        ctx = re.sub(r"\s+", " ", box.get_text(" ", strip=True))[:900]
        title = at if len(at) >= 12 and not GENERIC.search(at) else ""
        if not title:
            for h in box.find_all(["h2", "h3", "h4", "h5", "strong", "b", "td"]):
                ht = h.get_text(" ", strip=True)
                if len(ht) >= 12 and not GENERIC.search(ht):
                    title = ht
                    break
        title = re.sub(r"\s+", " ", title or "").strip(" -|:")[:260]
        if len(title) < 12 or SKIP.search(title) or not TENDER.search(title + " " + ctx[:300]):
            continue
        href = urljoin(page_url, a["href"]).split("#")[0]
        if not href.startswith("http") or re.search(r"facebook|twitter|linkedin|youtube|instagram|mailto:", href, re.I):
            continue
        dl = _deadline(ctx, t, mf)
        if not dl or dl < t:
            continue
        key = re.sub(r"\W+", "", title.lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        items.append({"title": title, "link": href, "deadline": dl.isoformat()})
    return items


def _subpages(base, text):
    sp = soup(text)
    host = urlparse(base).netloc
    out = []
    for a in sp.find_all("a", href=True):
        t = re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:80]
        u = urljoin(base, a["href"]).split("#")[0]
        if not u.startswith("http") or re.search(r"\.(pdf|docx?|xlsx?|zip)(\?|$)", u, re.I) or urlparse(u).netloc != host:
            continue
        if TENDER.search(t) and not SKIP.search(t) and len(t) < 60:
            out.append(u)
    return list(dict.fromkeys(out))[:3]


def scan(url, t, mf):
    st, final, txt = fetch(url, min_gap=1.5)
    if st != "ok":
        return st, []
    items = extract(final, txt, t, mf)
    if items:
        return "ok", items
    if len(txt) < 3000 or (("<app-root" in txt or 'id="root"' in txt or "__NEXT_DATA__" in txt) and len(re.sub(r"<[^>]+>", "", txt)) < 2500):
        return "js-only", []
    for u in _subpages(final, txt):
        st2, fin2, txt2 = fetch(u, min_gap=1.5)
        got = extract(fin2, txt2, t, mf) if st2 == "ok" else []
        if got:
            return "ok", got
    return "no-open-notices", []


def fetch():
    t = today()
    ts = str(t)
    entries = [e for e in csv.DictReader(open(LIST, encoding="utf-8")) if not e["covered"] and e["url"].startswith("http")]
    prev = {}
    if STATUS.exists():
        prev = {r["id"]: r for r in csv.DictReader(open(STATUS, encoding="utf-8"))}
    entries.sort(key=lambda e: (prev.get(e["id"], {}).get("checked", ""), e["id"]))
    start, out, stats = time.time(), [], {}

    def one(e):
        if time.time() - start > BUDGET_S:
            return e, None, []
        try:
            return (e,) + scan(e["url"], t, e["iso3"] in MONTH_FIRST)
        except Exception as ex:  # noqa: BLE001
            log.warning("directory500 %s: %s", e["id"], str(ex)[:80])
            return e, "error", []

    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(8) as ex:   # different hosts in parallel; il_web.fetch keeps the per-host gap
        results = list(ex.map(one, entries))
    for e, st, items in results:
        if st is None:
            continue
        for it in items:
            sector, how = classify(it["title"])
            out.append({"id": "D5-" + e["id"] + "-" + re.sub(r"\W+", "", it["title"].lower())[:50], "source": f"Directory sweep: {e['portal'] or e['entity']}"[:90],
                        "group": "", "sector": sector, "nature": "", "cpv": "", "classification": how, "country": e["iso3"],
                        "buyer": clean(e["entity"])[:120], "title": clean(it["title"])[:300],
                        "notice_type": f"Notice on the {e['type'].lower() or 'buyer'}'s tender page (generic extraction)",
                        "stage": "tender", "access": "Check the notice for eligibility of foreign suppliers",
                        "published": "", "deadline": it["deadline"], "deadline_basis": "page_text", "value": "", "currency": "",
                        "link": it["link"], "source_url": e["url"], "fetched": ts, "contact": "", "lang": ""})
        prev[e["id"]] = {"id": e["id"], "entity": e["entity"], "country": e["iso3"], "region": e["region"], "url": e["url"],
                         "status": st, "open_found": len(items), "checked": ts}
        stats[st] = stats.get(st, 0) + 1
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "entity", "country", "region", "url", "status", "open_found", "checked"])
        w.writeheader()
        w.writerows(sorted(prev.values(), key=lambda r: (str(r["id"]).startswith("B2-"), int(re.sub(r"\D", "", str(r["id"])) or 0))))
    rows, _ = rolling("directory500", out, max_age_days=90)
    log.info("Directory sweep: %d entries read this run (%s); %d open notices found now, %d kept", sum(stats.values()),
             ", ".join(f"{k} {v}" for k, v in sorted(stats.items())), len(out), len(rows))
    return rows, {"new": len(out), "entries_read": sum(stats.values()), **{f"st_{k}": v for k, v in stats.items()}}
