"""Company web profiles for the Supplier Universe: for suppliers with a known website (or a company e-mail domain),
reads the home page and a contact page and keeps the company's own description (what it makes / sells), role-based
e-mails (info@, sales@, export@ ...) and a phone number. Also tries to discover the website of strong suppliers that
have none, by checking likely domains and accepting one only when the page names the company.
Polite: robots.txt respected, short timeouts, no login/captcha pages. Results stay in the private cache."""
import csv
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .common import PRIVATE, log

UA = "Mozilla/5.0 (compatible; SinderSupplierResearch/1.0; +https://github.com/etaram/commodity-feeder)"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ROLE = re.compile(r"^(info|sales|export|exports|contact|contacto|contato|kontakt|office|trade|trading|commercial|comercial|"
                  r"vendas|ventas|enquiries|inquiries|hello|marketing|orders|business|bd|procurement|tender|tenders|"
                  r"admin|mail|general|customerservice|service|support|ventas1|info1)\b", re.I)
PHONE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,18}\d")
PATHS = ["", "contact", "contact-us", "contacts", "contacto", "contato", "kontakt", "en/contact", "about", "about-us"]
FREE = re.compile(r"@(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|ukr|i\.ua|meta\.ua|bigmir|web\.de|"
                  r"orange|free|laposte|wanadoo|libero|terra|uol|bol|ig|rediffmail|qq|163|126|sina|naver|hanmail|"
                  r"proton|zoho|seznam|wp\.pl|o2|interia|abv|btinternet|sky|comcast|verizon|att|sbcglobal|"
                  r"prodigy|telkomsa|mweb|iafrica|vodamail|yahoo\.co)\b", re.I)
PARKED = re.compile(r"domain (is )?for sale|buy this domain|parked|sedo|godaddy|dan\.com|hugedomains|"
                    r"this domain|coming soon|under construction|account suspended|index of /", re.I)
SLD = {"ZAF": "co.za", "BRA": "com.br", "COL": "com.co", "MEX": "com.mx", "ARG": "com.ar", "PER": "com.pe",
       "ECU": "com.ec", "KEN": "co.ke", "NGA": "com.ng", "GBR": "co.uk", "IND": "co.in", "TUR": "com.tr",
       "UGA": "co.ug", "TZA": "co.tz", "PRY": "com.py", "DOM": "com.do", "URY": "com.uy", "BOL": "com.bo",
       "GTM": "com.gt", "PAN": "com.pa", "CRI": "co.cr", "SLV": "com.sv", "HND": "hn", "NIC": "com.ni",
       "EGY": "com.eg", "MAR": "ma", "GHA": "com.gh", "ZMB": "co.zm", "ZWE": "co.zw", "ETH": "com.et",
       "PHL": "com.ph", "IDN": "co.id", "VNM": "com.vn", "THA": "co.th", "MYS": "com.my", "PAK": "com.pk",
       "BGD": "com.bd", "LKA": "lk", "NPL": "com.np", "AUS": "com.au", "NZL": "co.nz", "JPN": "co.jp",
       "KOR": "co.kr", "CHN": "com.cn", "UKR": "com.ua", "ISR": "co.il", "SAU": "com.sa", "ARE": "ae"}
PER_RUN, DISCOVER = 1500, 700
LEGAL = re.compile(r"\b(s\.?a\.?s?|ltda|ltd|limited|llc|inc|gmbh|ag|srl|s\.?r\.?l|spa|bv|nv|plc|pty|cc|co|corp|company|"
                   r"cia|sociedad|anonima|eireli|me|epp|sac|eirl|de|del|la|el|y|and|the|of|group|grupo|holding|tov|"
                   r"llc|ооо|тов|пп|фоп|ltda)\b", re.I)


def _session():
    s = requests.Session(); s.headers["User-Agent"] = UA
    return s


def _get(s, url):
    try:
        r = s.get(url, timeout=10, allow_redirects=True)
    except Exception:  # noqa: BLE001
        return None
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return None
    return r


def _meta(txt):
    for rx in (r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{20,400})',
               r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{20,400})',
               r'<meta[^>]+content=["\']([^"\']{20,400})["\'][^>]+name=["\']description'):
        m = re.search(rx, txt, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def _title(txt):
    m = re.search(r"<title[^>]*>(.*?)</title>", txt, re.I | re.S)
    return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:160] if m else ""


def profile(url):
    """{website, title, about, email, phone} from the home page and up to a few contact/about pages."""
    if not url.startswith("http"):
        url = "http://" + url
    s = _session()
    base = "{0.scheme}://{0.netloc}/".format(urlsplit(url))
    dom = urlsplit(base).netloc.lower().removeprefix("www.")
    rp = RobotFileParser()
    rr = _get(s, urljoin(base, "robots.txt"))
    rp.parse(rr.text.splitlines() if rr is not None else [])
    out = {"website": base, "title": "", "about": "", "email": "", "phone": ""}
    emails = []
    for path in PATHS:
        u = urljoin(base, path)
        if not rp.can_fetch(UA, u):
            continue
        r = _get(s, u)
        if r is None:
            continue
        if path == "":
            out["website"] = "{0.scheme}://{0.netloc}/".format(urlsplit(r.url))
            dom = urlsplit(r.url).netloc.lower().removeprefix("www.")
        txt = r.text[:500_000]
        if not out["title"]:
            out["title"] = _title(txt)
        if not out["about"]:
            out["about"] = _meta(txt)[:300]
        core = dom.split(".")[0] if dom.count(".") <= 1 else dom.split(".")[-3] if dom.endswith(tuple(SLD.values())) else dom.split(".")[-2]
        for e in EMAIL.findall(txt.replace("mailto:", " ")):
            e = e.strip(".").lower()
            if e.endswith((".png", ".jpg", ".gif", ".webp", ".svg", ".js", ".css")) or e in emails:
                continue
            if core and core in e.split("@")[1] and (ROLE.match(e.split("@")[0]) or len(emails) < 1):
                emails.append(e)
        if not out["phone"]:
            ph = PHONE.findall(re.sub(r"<[^>]+>", " ", txt))
            out["phone"] = ph[0].strip() if ph else ""
        if emails and out["about"] and path:
            break
        time.sleep(0.4)
    role = [e for e in emails if ROLE.match(e.split("@")[0])]
    out["email"] = "; ".join((role or emails)[:2])
    return out


def _tokens(name):
    t = re.sub(r"[^\w ]", " ", LEGAL.sub(" ", (name or "").lower()))
    return [w for w in t.split() if len(w) > 1 and not w.isdigit()]


def discover(name, country):
    """Website for a company with none on record: try likely domains, accept only a live, non-parked page whose
    title or text names the company."""
    tk = _tokens(name)
    if not tk or len(tk) > 4 or len("".join(tk)) < 4:
        return None
    slugs = list(dict.fromkeys(["".join(tk), "-".join(tk), "".join(tk[:2])] if len(tk) > 1 else [tk[0]]))
    tlds = [SLD.get(country), "com"] if SLD.get(country) else ["com"]
    s = _session()
    for slug in slugs[:2]:
        if len(slug) < 4:
            continue
        for tld in tlds:
            r = _get(s, f"http://{slug}.{tld}/")
            if r is None:
                continue
            txt = r.text[:200_000]
            low = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt)).lower()
            if PARKED.search(low[:5000]):
                continue
            title = _title(txt).lower()
            hits = sum(1 for w in tk if len(w) > 2 and (w in title or low.count(w) >= 2))
            if hits >= max(1, min(2, len([w for w in tk if len(w) > 2]))):
                return "{0.scheme}://{0.netloc}/".format(urlsplit(r.url))
    return None


DEADLINE = [float("inf")]


def _safe(f, *a):
    if time.time() > DEADLINE[0]:
        return None
    try:
        return f(*a)
    except Exception:  # noqa: BLE001
        return None


def fetch():
    src = PRIVATE / "universe.csv"
    if not src.exists():
        return [], {"note": "no universe yet"}
    t_end = time.time() + 1440
    prof_p = PRIVATE / "web_profiles.jsonl"
    profiles = {}
    if prof_p.exists():
        for line in prof_p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line); profiles[d["key"]] = d
            except (ValueError, KeyError):
                pass
    tried_p = PRIVATE / "web_discover_tried.txt"
    tried = set(tried_p.read_text(encoding="utf-8").split("\n")) if tried_p.exists() else set()
    todo, disc = [], []
    for r in csv.DictReader(open(src, encoding="utf-8")):  # sorted by quality
        w = (r.get("website") or "").strip()
        em = (r.get("email") or "").split(";")[0].strip()
        if not w and em and "@" in em and not FREE.search(em):
            w = "http://" + em.split("@")[1]
        key = f"{r['supplier']}|{r['country']}"
        if w:
            if key not in profiles and len(todo) < PER_RUN:
                todo.append((key, w))
        elif key not in tried and len(disc) < DISCOVER and int(r.get("quality") or 0) >= 35:
            disc.append((key, r["supplier"], r["country"]))
        if len(todo) >= PER_RUN and len(disc) >= DISCOVER:
            break
    found = 0
    disc_keys = {k for k, _, _ in disc}
    with ThreadPoolExecutor(max_workers=24) as ex:
        DEADLINE[0] = t_end - 900  # discovery gets at most ~9 minutes
        for (key, name, country), url in zip(disc, ex.map(lambda x: _safe(discover, x[1], x[2]), disc)):
            tried.add(key)
            if url:
                found += 1; todo.append((key, url))
        DEADLINE[0] = t_end - 30
        prof = 0
        with open(prof_p, "a", encoding="utf-8") as f:
            for (key, url), res in zip(todo, ex.map(lambda x: _safe(profile, x[1]), todo)):
                if res is None and time.time() > DEADLINE[0]:
                    continue
                res = res or {"website": "", "title": "", "about": "", "email": "", "phone": ""}
                res["key"] = key; res["discovered"] = key in disc_keys
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                prof += 1
                if time.time() > t_end:
                    break
    tried_p.write_text("\n".join(sorted(tried)), encoding="utf-8")
    log.info("web profiles: %d read, %d websites discovered of %d tried", prof, found, len(disc))
    return [], {"profiles": prof, "discovered": found, "tried": len(disc)}
