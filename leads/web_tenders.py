"""Generic extraction of tender notices from English-language procurement web pages (US cities and agencies).
Same approach as il_web (anchors and their table row / list item), with English vocabulary and US dates."""
import datetime as dt
import re
from urllib.parse import urljoin, urlparse

from .il_web import fetch, soup  # polite fetching with robots.txt and per-host gaps

TENDER = re.compile(r"\b(RFPs?|RFQs?|RFIs?|IFBs?|ITBs?|RFBs?|RFSQs?|RFQuals?|solicitations?|invitations? (?:to|for) bids?|"
                    r"requests? for (?:proposals?|quotes?|quotations?|qualifications|bids?|information)|bid (?:no\.?|number|#)|"
                    r"sealed bids?|notice to bidders|bid opportunit(?:y|ies)|formal bids?|informal bids?)\b", re.I)
NAV = re.compile(r"^(bids?|bid opportunities|current bids|open bids|solicitations|current solicitations|open solicitations|"
                 r"bids and proposals|bids & proposals|procurement|purchasing|contracting opportunities|business opportunities|"
                 r"view (?:all )?(?:bids|solicitations)|doing business with the city)$", re.I)
SKIP = re.compile(r"\b(job|jobs|career|employment|position|internship|awarded|award notice|bid results|bid tabulation|"
                  r"tabulations?|closed|cancel(?:l)?ed|archive|addend(?:um|a)|pre-?bid (?:meeting|conference)|minutes|"
                  r"how to|instructions|register|registration|login|sign in|vendor guide|faq|policy|ordinance)\b", re.I)
GENERIC = re.compile(r"^(click here|more|details|view|download|pdf|read more|learn more|here|link)$", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
D_NUM = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?!\d)")
D_ISO = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)(?!\d)")
D_TXT = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d\d)\b", re.I)
DUE = re.compile(r"due|clos(?:e|es|ing)|deadline|opening|open date|submit", re.I)


def dates(s, today):
    out = []
    for m, d, y in D_NUM.findall(s):
        y = int(y) + (2000 if len(y) == 2 else 0)
        out.append((y, int(m), int(d)))
    out += [(int(y), int(m), int(d)) for y, m, d in D_ISO.findall(s)]
    out += [(int(y), MONTHS[m[:3].lower()], int(d)) for m, d, y in D_TXT.findall(s)]
    res = []
    for y, m, d in out:
        try:
            x = dt.date(y, m, d)
        except ValueError:
            continue
        if 2015 <= x.year <= today.year + 3:
            res.append(x)
    return res


def deadline(ctx, today):
    for m in DUE.finditer(ctx):
        ds = dates(ctx[m.start(): m.start() + 90], today)
        if ds:
            return ds[0]
    ds = dates(ctx, today)
    fut = [d for d in ds if d >= today]
    return max(fut) if fut else (max(ds) if ds else None)


def extract(page_url, text, today=None):
    today = today or dt.date.today()
    sp = soup(text)
    for t in sp(["script", "style", "noscript", "header", "footer", "nav"]):
        t.decompose()
    items, seen = [], set()
    for a in sp.find_all("a", href=True):
        at = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        box = a
        for _ in range(6):
            p = box.parent
            if p is None or p.name in ("body", "html", "main", "form"):
                break
            if len(p.get_text(" ", strip=True)) > 800:
                break
            box = p
            if p.name in ("tr", "li", "article"):
                break
        ctx = re.sub(r"\s+", " ", box.get_text(" ", strip=True))[:800]
        if NAV.search(at.strip()):
            continue
        title = at if len(at) >= 12 and not GENERIC.search(at) else ""
        if not title:
            for h in box.find_all(["h2", "h3", "h4", "h5", "strong", "b", "td"]):
                ht = h.get_text(" ", strip=True)
                if len(ht) >= 12 and not GENERIC.search(ht):
                    title = ht
                    break
        title = re.sub(r"\s+", " ", title or ctx).strip(" -|:")[:260]
        if len(title) < 12 or SKIP.search(title):
            continue
        if not TENDER.search(title + " " + ctx[:300]):
            continue
        dl = deadline(ctx, today)
        if dl and dl < today:
            continue
        key = re.sub(r"\W+", "", title.lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        num = re.search(r"\b(?:RFP|RFQ|IFB|ITB|RFB|RFI|bid|solicitation)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-./]{2,24})", title + " " + ctx, re.I)
        items.append({"title": title, "link": urljoin(page_url, a["href"]).split("#")[0], "deadline": dl.isoformat() if dl else "",
                      "number": num.group(1) if num else "", "context": ctx[:400]})
    return items


def candidate_links(base_url, text):
    sp = soup(text)
    host = urlparse(base_url).netloc.replace("www.", "")
    scored = {}
    for a in sp.find_all("a", href=True):
        t = re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:80]
        u = urljoin(base_url, a["href"].strip()).split("#")[0]
        if not u.startswith("http") or re.search(r"\.(pdf|docx?|xlsx?|zip)(\?|$)", u, re.I):
            continue
        sc = 0
        if NAV.search(t):
            sc += 10
        elif re.search(r"bid|solicitation|rfp|opportunit", t, re.I) and len(t) < 50:
            sc += 6
        if re.search(r"bid|solicit|rfp|opportunit|procure|purchas|bonfire|planetbids|opengov|bidnet|biddingo", u, re.I):
            sc += 4
        if SKIP.search(t) or re.search(r"job|career", u, re.I):
            sc -= 12
        uh = urlparse(u).netloc.replace("www.", "")
        if uh != host and not re.search(r"bonfire|planetbids|opengov|bidnet|biddingo|ionwave|buyspeed|bso", u, re.I):
            sc -= 3
        if sc > 4:
            scored[u] = max(scored.get(u, 0), sc)
    return [u for u, _ in sorted(scored.items(), key=lambda x: -x[1])]


def scan_page(url, depth=1):
    """Notices on url; if none, follow the best tender links (depth levels). Returns (page_used, items)."""
    st, final, txt = fetch(url, min_gap=1.5)
    if st != "ok":
        return url, [], st
    items = extract(final, txt)
    if len(items) >= 2 or depth <= 0:
        return final, items, "ok"
    best = (final, items, "ok")
    for u in candidate_links(final, txt)[:4]:
        page, got, s2 = scan_page(u, depth - 1)
        if len(got) > len(best[1]):
            best = (page, got, s2)
    return best
