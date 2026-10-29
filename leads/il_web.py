"""Shared helpers for the Israel monitor: polite fetching with robots.txt, link discovery and notice extraction."""
import datetime as dt
import re
import threading
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

TENDER_TXT = re.compile(r"מכרז|מכרזים|קול קורא|קולות קוראים|קול-קורא|הזמנה להציע|הזמנה להגיש|בקשה לקבלת הצעות|"
                        r"בקשה להצעות|בקשה להציע|פנייה לקבלת הצעות|פניה לקבלת הצעות|הליך תחרותי|הליך פנייה|"
                        r"\bRFP\b|\bRFI\b|\bRFQ\b|התקשרות בפטור|הודעה על כוונה להתקשר|מכרז פומבי|מכרז זוטא|"
                        r"\btenders?\b|procurement|הליכי רכש|הודעות רכש|רכש והתקשרויות", re.I)
NAV_TXT = re.compile(r"^(מכרזים|מכרזים וקולות קוראים|מכרזים ודרושים|קולות קוראים|מכרזים והתקשרויות|הליכי רכש|"
                     r"מכרזים פעילים|מכרזים והודעות|tenders|procurement|מכרזים ורכש|רכש|מכרזים וספקים|מכרזים והצעות מחיר|"
                     r"מכרזי רכש|מכרזים פומביים|מכרזים והליכי רכש|מכרזים ופניות|מכרזים - .{0,20})$", re.I)
JOB = re.compile(r"משרה|משרת|דרוש|דרושים|דרושות|כוח אדם|כח אדם|כ\"א|מכרז פנימי|מכרז חיצוני|מכרז פנימי/חיצוני|"
                 r"/ת\b|\(ת\)|מזכיר/ה|עובד/ת|רכז/ת|מנהל/ת|עו\"ס|גננת|סייעת|לתפקיד|תפקיד|קריירה|career|jobs?\b|"
                 r"משאבי אנוש|היקף משרה|תקן|מלגה|מלגות|הנחה בארנונה|ועדת השמות", re.I)
SALE = re.compile(r"השכרת|להשכרה|מכירת|למכירה|חכירה|הקצאת קרקע|הקצאת מבנה|הרשמה להגרלה|דירה|מגרש|הפעלת קיוסק|"
                  r"הפעלת מזנון|הפעלת קפיטריה|זיכיון", re.I)
GENERIC = re.compile(r"^(לחץ כאן|לחצו כאן|קרא עוד|קראו עוד|למידע נוסף|לפרטים|לפרטים נוספים|פרטים|הורדה|להורדה|"
                     r"מסמכי המכרז|מסמכים|צפייה|לצפייה|pdf|docx?|קובץ|נספח.*|עוד|more|download|view)$", re.I)
DATE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)")
DEADLINE_CUE = re.compile(r"מועד אחרון|הגשה|להגשה|יוגשו|תאריך סגירה|סגירה|עד ליום|עד יום|עד לתאריך|deadline", re.I)
NUMBER = re.compile(r"(?:מכרז|קול קורא|הליך|פנייה|בקשה)[^\d\n]{0,18}(?:מס['׳\"]?|מספר)?\s*[:.]?\s*(\d{1,4}[/\-.]\d{2,4}|\d{1,5})")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
      "SinderTenderMonitor/1.0")

_robots, _rlock = {}, threading.Lock()
_last, _llock = {}, threading.Lock()


def _session():
    from curl_cffi import requests as cr
    return cr.Session(impersonate="chrome", timeout=30, headers={"Accept-Language": "he,en;q=0.8"})


_tls = threading.local()


def _s():
    if not hasattr(_tls, "s"):
        _tls.s = _session()
    return _tls.s


def allowed(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    with _rlock:
        rp = _robots.get(base)
    if rp is None:
        rp = RobotFileParser()
        try:
            r = _s().get(base + "/robots.txt", timeout=15)
            if r.status_code == 200 and "html" not in (r.headers.get("content-type") or "").lower():
                rp.parse(r.text.splitlines())
            else:
                rp.parse([])
        except Exception:  # noqa: BLE001
            rp.parse([])
        with _rlock:
            _robots[base] = rp
    try:
        return rp.can_fetch("SinderTenderMonitor", url) and rp.can_fetch("*", url)
    except Exception:  # noqa: BLE001
        return True


def fetch(url, min_gap=2.0):
    """GET with robots.txt check and at least min_gap seconds between requests to the same host.
    Returns (status, final_url, text) where status is 'ok', 'robots', 'http-<code>', 'blocked' or 'error'."""
    if not allowed(url):
        return "robots", url, ""
    host = urlparse(url).netloc
    with _llock:
        wait = _last.get(host, 0) + min_gap - time.time()
        _last[host] = max(time.time(), _last.get(host, 0) + min_gap)
    if wait > 0:
        time.sleep(wait)
    try:
        r = _s().get(url, allow_redirects=True)
    except Exception:  # noqa: BLE001
        return "error", url, ""
    txt = r.text or ""
    if r.status_code != 200:
        return f"http-{r.status_code}", str(r.url), ""
    low = txt[:4000].lower()
    if ("captcha" in low or "cf-chl" in low or "incapsula" in low or "access denied" in low) and len(txt) < 20000:
        return "blocked", str(r.url), ""
    return "ok", str(r.url), txt


def soup(text):
    return BeautifulSoup(text, "lxml")


def candidate_links(base_url, text):
    """Links on a page that lead to a tenders / calls page, best first."""
    sp = soup(text)
    host = urlparse(base_url).netloc.replace("www.", "")
    scored = {}
    for a in sp.find_all("a", href=True):
        t = re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:80]
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        u = urljoin(base_url, href).split("#")[0]
        uh = urlparse(u).netloc.replace("www.", "")
        if not uh or (uh != host and not uh.endswith("." + host) and not host.endswith("." + uh)
                      and not re.search(r"tender|michraz|mihraz|bids|procure|rechesh|ecomm|e-?tender", u, re.I)):
            continue
        if re.search(r"\.(pdf|docx?|xlsx?|zip|jpg|png)(\?|$)", u, re.I):
            continue
        sc = 0
        if NAV_TXT.search(t):
            sc += 12
        elif re.search(r"מכרז|קול(ות)? קור", t):
            sc += 7 if len(t) < 40 else 2
        if re.search(r"tender|michraz|mihraz|mikhraz|bids|procure|rechesh|kolot|kol-kore|calls", u, re.I):
            sc += 6
        if JOB.search(t) or re.search(r"jobs|career|drushim|mishrot", u, re.I):
            sc -= 15
        if re.search(r"ארכיון|archive|זוכים|תוצאות", t + u, re.I):
            sc -= 4
        if sc > 4:
            scored[u] = max(scored.get(u, 0), sc)
    return [u for u, _ in sorted(scored.items(), key=lambda x: -x[1])]


def _dates(s, today):
    out = []
    for d, m, y in DATE.findall(s):
        y = int(y) + (2000 if len(y) == 2 else 0)
        try:
            x = dt.date(y, int(m), int(d))
        except ValueError:
            continue
        if 2015 <= x.year <= today.year + 3:
            out.append(x)
    return out


def _deadline(ctx, today):
    best = None
    for m in DEADLINE_CUE.finditer(ctx):
        ds = _dates(ctx[m.start(): m.start() + 80], today)
        if ds:
            best = ds[0]
            break
    ds = _dates(ctx, today)
    if not best and ds:
        fut = [d for d in ds if d >= today]
        best = max(fut) if fut else max(ds)
    pub = min(ds) if ds else None
    return best, pub


def extract(page_url, text, today=None):
    """Notices on a tenders page: title, link, number, deadline, published. Jobs, sales and navigation removed."""
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
            pt = p.get_text(" ", strip=True)
            if len(pt) > 700:
                break
            box = p
            if p.name in ("tr", "li", "article") or any(c for c in (p.get("class") or [])
                                                           if re.search(r"item|row|card|tender|result|entry|post", c, re.I)):
                break
        ctx = re.sub(r"\s+", " ", box.get_text(" ", strip=True))[:700]
        if not TENDER_TXT.search(ctx + " " + at) or NAV_TXT.search(at.strip()):
            continue
        title = at if len(at) >= 12 and not GENERIC.search(at) else ""
        if not title:
            for h in box.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b"]):
                ht = h.get_text(" ", strip=True)
                if len(ht) >= 12:
                    title = ht
                    break
        if not title:
            title = ctx
            m = DEADLINE_CUE.search(title)
            if m and m.start() > 15:
                title = title[:m.start()]
        title = re.sub(r"\s+", " ", title).strip(" -|:")[:260]
        if len(title) < 12 or JOB.search(title) or SALE.search(title):
            continue
        if not TENDER_TXT.search(title + " " + ctx[:200]):
            continue
        link = urljoin(page_url, a["href"]).split("#")[0]
        key = re.sub(r"\W+", "", title)[:90]
        if key in seen:
            continue
        seen.add(key)
        dl, pub = _deadline(ctx, today)
        num = NUMBER.search(title + " " + ctx)
        kind = "call" if re.search(r"קול(ות)? קור", title + ctx[:150]) else "tender"
        items.append({"title": title, "link": link, "number": num.group(1) if num else "",
                      "deadline": dl.isoformat() if dl else "", "published": pub.isoformat() if pub else "",
                      "kind": kind, "context": ctx[:400]})
    return items
