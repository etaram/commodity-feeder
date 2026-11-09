"""Company checks: a background job that reads a supplier's own website and records, in code (no model calls), what the
site actually says, so a match or a sector is backed by the company's own words and a contact by its own domain.

Per company, at most 6 pages of its own site (home, then about / products / contact pages found from the home page's
links), robots.txt respected, one request at a time per host with a pause, 10 s timeout, 600 KB per page:
  alive         the site answers, is not parked or "coming soon", and where it redirects
  name_match    how well the page names the company (tokens of the legal name in title / text): high, partial, none
  domain        the final domain; e-mails kept only on that domain (generic sales channel vs named contact)
  description   the site's own description (meta, then the first substantial paragraph)
  products      product and service phrases from headings, menus and product lists
  sector        the sector the site's own text gives (leads.sectors.classify), compared with the record's sector
  role          manufacturer / trader-distributor / EPC-contractor / service signals, each with the phrase that set it
  certificates  ISO 9001 / 14001 / 45001 / 22000 / 13485, CE, API, ASME, HACCP, GMP, FSSC, halal, kosher, UL, IECEx...
  export        export wording and the countries the site names
  legal ids     VAT / CNPJ / CIN / company registration numbers printed on the site
  phones        international-format numbers found on the site
  verdict       ok / name mismatch / parked / unreachable / blocked by robots / no website, plus the gaps

Queue (value of information first): companies people asked to check from the panel ('Check queue' tab), companies
people opened or searched (Activity), proven suppliers whose sector is unknown or flagged, proven suppliers never
checked, then rechecks older than 90 days. Each check is stored with a content hash; an unchanged site is not
re-parsed. Results: data/checks/company_checks.jsonl (private, kept in the Actions cache) and the private sheet tab
'Company checks' for the panel; leads/universe.py reads them as the company's own description.

  python -m leads.company_check [--limit N] [--minutes M]
"""
import csv
import hashlib
import html
import json
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .common import DATA, PRIVATE, log
from .sectors import _KW, SECTORS

CHECKS = DATA / "checks"
OUT = CHECKS / "company_checks.jsonl"
UA = "Mozilla/5.0 (compatible; SinderCompanyCheck/1.0; +https://github.com/etaram/commodity-feeder)"
VERSION = "check-4"
RECHECK_DAYS = 90
MAX_PAGES = 8
PAGE_BYTES = 600_000

LEGAL = re.compile(r"\b(s\.?a\.?s?|ltda|ltd|limited|llc|inc|gmbh|ag|kg|srl|s\.?r\.?l|spa|s\.?p\.?a|bv|nv|plc|pty|cc|co|corp|"
                   r"corporation|company|group|holding|sarl|sa de cv|de cv|cia|eirl|sac|oy|ab|as|a/s|kft|zrt|sp z o o|"
                   r"jsc|ojsc|pjsc|ooo|tov|llp|pvt|private|public|enterprises?|international|industries|trading|the|and|of|et|y|e)\b", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GENERIC = re.compile(r"^(info|sales|export|exports|contact|contacto|contato|kontakt|office|trade|trading|commercial|comercial|"
                     r"vendas|ventas|enquiries|inquiries|hello|marketing|orders|business|bd|procurement|tender|tenders|admin|"
                     r"mail|general|customerservice|service|support|ventes|vertrieb|verkauf)\b", re.I)
PHONE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,18}\d")
PERSON = re.compile(r"[a-z]{1,}[._-][a-z]{2,}(?:[._-][a-z]{2,})?")
DEPT = re.compile(r"press|media|news|pr\b|marketing|kund|customer|client|cliente|legal|compliance|sponsor|social|rrhh|hr\b|jobs|career|"
                  r"recruit|operacion|servicio|support|service|help|billing|invoice|factur|account|privacy|gdpr|webmaster|noreply|info", re.I)
PARKED = re.compile(r"domain (is )?for sale|buy this domain|this domain (may be|is) for sale|parked (free|domain)|sedo\.com|"
                    r"hugedomains|dan\.com|coming soon|under construction|account (has been )?suspended|index of /|"
                    r"website is (currently )?(under|being)|default web site page|welcome to nginx|it works!", re.I)
LINK_HINT = re.compile(r"about|company|who-we-are|quienes|empresa|nosotros|sobre|unternehmen|societe|chi-siamo|profile|"
                       r"product|products|productos|produtos|produits|produkte|solutions|services|catalog|catalogue|range|"
                       r"contact|contacto|contato|kontakt|impressum|export|certific|quality|calidad|qualidade", re.I)
ROLE_RULES = [
    ("manufacturer", re.compile(r"\b(we (manufacture|produce)|manufacturer of|leading manufacturer|producer of|our (factory|plant|mill|production (line|facility|plant)s?)|"
                                r"production capacity|manufacturing (facility|plant|site)|fabricante|fabricamos|fabricação|fabrique|fabricant|hersteller|"
                                r"produzent|produttore|ISO 9001 certified (factory|plant)|tonnes per (year|day|annum)|tons per (year|day))\b", re.I)),
    # exporting is not trading: a manufacturer exports too, so export wording is recorded apart (EXPORT)
    ("trader", re.compile(r"\b(we are (a|an|the) (leading )?(distributor|importer|wholesaler)|official distributor (of|for)|trading company|we (distribute|import|resell)|importer (of|and)|wholesale(r|rs)?|"
                          r"authori[sz]ed (dealer|distributor|agent)|sole agent|representative of|distribuidor|importador|"
                          r"comercializadora|négoce|distributeur|großhandel|händler)\b", re.I)),
    ("epc", re.compile(r"\b(EPC|engineering,? procurement and construction|general contractor|main contractor|design and build|"
                       r"installation (and|&) commissioning|contratista|empreiteira|entreprise générale)\b", re.I)),
    ("service", re.compile(r"\b(consulting (firm|company|services)|consultancy|advisory (firm|services)|maintenance services|cleaning services|security services|"
                           r"guarding|staffing agency|software (company|development company)|it services|marketing agency|law firm|accounting firm|"
                           r"engineering consultancy|catering services|facility management)\b", re.I)),
]
# role phrases count only in the company's own description, title and about pages, never in careers, news or menus
ROLE_PAGE = re.compile(r"about|company|who-we-are|quienes|empresa|nosotros|sobre|unternehmen|societe|profile|^/$", re.I)
CERTS = re.compile(r"\b(ISO\s?9001|ISO\s?14001|ISO\s?45001|OHSAS\s?18001|ISO\s?22000|ISO\s?13485|ISO\s?27001|ISO\s?50001|IATF\s?16949|"
                   r"AS\s?9100|FSSC\s?22000|HACCP|GMP certified|BRCGS|IFS Food|CE mark(?:ing|ed)?|API\s?(?:5L|6D|Q1)|ASME [A-Z]|"
                   r"UL listed|IECEx|ATEX|[Hh]alal certified|[Kk]osher certified|USDA [Oo]rganic|INMETRO|NSF/ANSI|WRAS|DVGW|KEMA-KEUR)\b")
EXPORT = re.compile(r"\b(export(s|ing|ed)? to|we export|exporting to|our export|countries worldwide|in over \d+ countries|"
                    r"more than \d+ countries|\d+\+? countries|exportamos|exportações|exportons|exportieren)\b", re.I)
LEGAL_ID = [
    ("CNPJ", re.compile(r"\bCNPJ[:\s]*([\d./-]{14,20})")),
    ("CIN", re.compile(r"\bCIN[:\s]*([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})")),
    ("GSTIN", re.compile(r"\bGSTIN?[:\s]*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2})")),
    ("VAT", re.compile(r"\b(?:VAT|USt-?IdNr\.?|TVA|P\.?\s?IVA|NIF|CIF)[\s.:No]*([A-Z]{2}\s?[\dA-Z]{8,12})")),
    ("RUC", re.compile(r"\bRUC[:\s]*(\d{10,13})")),
    ("NIT", re.compile(r"\bNIT[:\s]*([\d.-]{8,15})")),
    ("RFC", re.compile(r"\bRFC[:\s]*([A-Z&Ñ]{3,4}\d{6}[A-Z\d]{3})")),
    ("Company no.", re.compile(r"\b(?:Company|Registration|Reg\.?) (?:No|Number)\.?[:\s]*([A-Z]{0,2}\d{6,10})", re.I)),
    ("KRS", re.compile(r"\bKRS[:\s]*(\d{10})")),
    ("HRB", re.compile(r"\bHR[AB][:\s]*(\d{3,7})")),
]
STRIP = re.compile(r"<(script|style|noscript|svg|template)[^>]*>.*?</\1>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")


def _country_names():
    try:
        d = json.loads((Path(__file__).resolve().parents[1] / "dealdesk" / "lib" / "countrynames.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for iso, names in d.items():
        for n in names:
            if len(n) >= 4:
                out.append((iso, re.compile(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])")))
    return out


COUNTRIES = _country_names()


def tokens(name):
    t = re.sub(r"[^\w ]", " ", LEGAL.sub(" ", (name or "").lower()))
    return [w for w in t.split() if len(w) > 2 and not w.isdigit()]


def text_of(page):
    t = STRIP.sub(" ", page)
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", t, flags=re.I)
    t = html.unescape(TAG.sub(" ", t))
    return re.sub(r"[ \t\r\f\v]+", " ", t)


def meta_description(page):
    for rx in (r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{20,500})',
               r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{20,500})',
               r'<meta[^>]+content=["\']([^"\']{20,500})["\'][^>]+name=["\']description'):
        m = re.search(rx, page, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def title_of(page):
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:200] if m else ""


def headings(page):
    """Product and service phrases: h1-h3 text, menu entries and list items inside product-like sections."""
    out = []
    for m in re.finditer(r"<h[1-3][^>]*>(.*?)</h[1-3]>", page, re.I | re.S):
        t = html.unescape(TAG.sub(" ", m.group(1))).strip()
        if 3 <= len(t) <= 80:
            out.append(re.sub(r"\s+", " ", t))
    for m in re.finditer(r'<a[^>]+href=["\'][^"\']*(product|produc|solution|categor|range|catalog)[^"\']*["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        t = html.unescape(TAG.sub(" ", m.group(2))).strip()
        if 3 <= len(t) <= 60:
            out.append(re.sub(r"\s+", " ", t))
    seen, res = set(), []
    for t in out:
        k = t.lower()
        if k in seen or not product_like(t):
            continue
        seen.add(k); res.append(t)
    return res[:40]


NAV = re.compile(r"^(home|start|inicio|accueil|startseite|about|about us|who we are|our company|company|profile|contact|contact us|kontakt|contacto|"
                 r"impressum|imprint|legal|privacy|cookies?|cookie settings|news|newsroom|press|media|media hub|blog|events?|careers?|jobs|"
                 r"join us|investors?|investor relations|sustainability|esg|our mission|mission|vision|values|history|leadership|"
                 r"products?|services?|solutions?|our solutions|our services|our products|read more|learn more|more|menu|main navigation|"
                 r"navigation|search|login|sign in|shop|onlineshop|downloads?|resources|support|faq|english|deutsch|español|français|"
                 r"choose your country or region|select your region|social media|follow us|subscribe|newsletter|"
                 r"quienes somos|nosotros|misi[oó]n|visi[oó]n|noticias|aktuelles|über uns|unternehmen|konzern|qui sommes-nous|"
                 r"actualit[eé]s|carri[eè]res|a propos)$", re.I)


def product_like(t):
    """A heading that names a product or a product line, not a slogan, a news title, a menu item or a figure."""
    t = t.strip()
    words = t.split()
    if not (1 <= len(words) <= 7) or len(t) > 70:
        return False
    if NAV.match(t.strip(" .:!?-").lower()):
        return False
    if re.search(r"[.!?:]\s*$|[“”\"«»]|\b(20[12]\d|19\d\d)\b|\d+\s?%|[£$€]\s?\d|\bwe\b|\bour\b|\byou(r)?\b|\bnous\b|\bwir\b|\bnuestr|\bsomos\b", t, re.I):
        return False  # sentences, quotes, dated news, figures, slogans in the first or second person
    if re.fullmatch(r"[\d\W]+", t) or re.search(r"cookie|privacy|gdpr|terms (of|and)|datenschutz|privacidad|confidentialit", t, re.I):
        return False
    return True


def name_match(name, title, text):
    from .zh_names import is_cjk, page_names
    if is_cjk(name):
        return page_names(name, title, text)  # Chinese names: the full name or a core name shown on the page
    tk = tokens(name)
    if not tk:
        return "unknown", 0
    low_t, low = title.lower(), text.lower()
    hits = sum(1 for w in tk if w in low_t or low.count(w) >= 2)
    share = hits / len(tk)
    return ("high" if share >= 0.67 else "partial" if share > 0 else "none"), round(share, 2)


def site_domain(url):
    h = urlsplit(url).netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def core_of(domain):
    parts = domain.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "net", "gov", "ac", "edu"):
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else domain


def emails_on(text, domain):
    core = core_of(domain)
    out = []
    for e in EMAIL.findall(text.replace("mailto:", " ")):
        e = e.strip(".").lower()
        if e.endswith((".png", ".jpg", ".gif", ".webp", ".svg", ".js", ".css")) or e in (x["email"] for x in out):
            continue
        d = e.split("@")[1]
        box = e.split("@")[0]
        if re.fullmatch(r"x+|test|example|name|email|your\.?name", box):
            continue
        if core and (d == domain or d.endswith("." + domain) or core_of(d) == core):
            kind = "generic" if GENERIC.match(box) else "named" if PERSON.fullmatch(box) and not DEPT.search(box) else "department"
            out.append({"email": e, "kind": kind})
    return out[:6]


# the company's own LinkedIn page and WhatsApp numbers, as linked from its own site (share buttons and personal profiles
# are not the company's channel)
LINKEDIN = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(company|school|showcase)/([A-Za-z0-9\-_%.]{2,100})", re.I)
WHATSAPP = re.compile(r"(?:https?://)?(?:wa\.me/|(?:api|web)\.whatsapp\.com/send/?\?(?:[^\"'<>\s]*?&(?:amp;)?)?phone=|whatsapp://send/?\?phone=)\+?(\d[\d\s().-]{6,20}\d)", re.I)


def social_on(raw_pages):
    """raw_pages: html of one site's pages. Returns (linkedin url or "", [whatsapp numbers in +<digits> form])."""
    li, wa = "", []
    for page in raw_pages:
        for kind, slug in LINKEDIN.findall(page):
            slug = slug.strip(".").split("?")[0]
            if not li and slug.lower() not in ("linkedin", "company", "showcase"):
                li = f"https://www.linkedin.com/{kind.lower()}/{slug}"
        for num in WHATSAPP.findall(page):
            d = re.sub(r"\D", "", num)
            if 8 <= len(d) <= 15 and "+" + d not in wa and not re.fullmatch(r"(\d)\1+", d):
                wa.append("+" + d)
    return li, wa[:3]


# schema.org data a site publishes for search engines (JSON-LD): its own structured statement of name, address,
# phone, registration ids, social profiles and products. More exact than headings, still the company's own claim.
LDJSON = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.I | re.S)
ORG_TYPES = re.compile(r"Organization|Corporation|LocalBusiness|Store|Manufacturer|Company|MedicalOrganization|NGO", re.I)
PROD_TYPES = re.compile(r"^(Product|ProductModel|IndividualProduct|Service|Offer)$", re.I)


def _ld_items(page):
    out = []
    for m in LDJSON.finditer(page):
        raw = html.unescape(m.group(1).strip())
        try:
            j = json.loads(raw)
        except ValueError:
            continue
        stack = [j]
        while stack and len(out) < 300:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                out.append(x)
                for k in ("@graph", "itemListElement", "item", "mainEntity", "hasOfferCatalog", "makesOffer", "offers", "itemOffered", "brand", "manufacturer"):
                    if k in x:
                        stack.append(x[k])
    return out


def _s(v):
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):
        v = v.get("name") or v.get("@id") or ""
    return re.sub(r"\s+", " ", str(v or "")).strip()


def structured_on(raw_pages):
    """The site's own schema.org Organization record and product names (pure)."""
    org, prods = {}, []
    for page in raw_pages:
        for x in _ld_items(page):
            t = " ".join(x.get("@type")) if isinstance(x.get("@type"), list) else str(x.get("@type") or "")
            if ORG_TYPES.search(t) and not org.get("name"):
                a = x.get("address") or {}
                if isinstance(a, list):
                    a = a[0] if a else {}
                addr = ", ".join(_s(a.get(k)) for k in ("streetAddress", "postalCode", "addressLocality", "addressRegion", "addressCountry") if isinstance(a, dict) and _s(a.get(k))) if isinstance(a, dict) else _s(a)
                same = x.get("sameAs") or []
                same = [same] if isinstance(same, str) else [u for u in same if isinstance(u, str)]
                org = {k: v for k, v in {
                    "name": _s(x.get("name"))[:150], "legal_name": _s(x.get("legalName"))[:150], "address": addr[:250],
                    "telephone": _s(x.get("telephone"))[:40], "email": _s(x.get("email")).replace("mailto:", "")[:120],
                    "vat": _s(x.get("vatID"))[:30], "tax_id": _s(x.get("taxID"))[:30], "lei": _s(x.get("leiCode"))[:20], "duns": _s(x.get("duns"))[:15],
                    "founded": _s(x.get("foundingDate"))[:10], "employees": _s((x.get("numberOfEmployees") or {}).get("value") if isinstance(x.get("numberOfEmployees"), dict) else x.get("numberOfEmployees"))[:12],
                    "same_as": [u[:200] for u in same[:12]]}.items() if v}
            elif PROD_TYPES.search(t.strip()):
                n = _s(x.get("name"))[:120]
                if n and n not in prods and product_like(n):
                    prods.append(n)
    return org, prods[:40]


# words every corporate site carries: they say nothing about what the company sells
NOISE = re.compile(r"\b(investor relations?|information|solutions?|innovation|digital|services?|security|cookies?|privacy|"
                   r"sustainab\w*|careers?|news(room)?|media|licen[cs]e\w*|research|translational)\b", re.I)


def site_sector(lead, products):
    """Sector from the site's own words by scoring every sector's keywords (not the first one that matches): the title
    and description count double, product headings once; a winner needs 2 points and a clear lead, else unclear."""
    lead_t, prod_t = NOISE.sub(" ", lead), NOISE.sub(" ", " ; ".join(products[:25]))
    score = defaultdict(float)
    # the tender keyword lists match word stems; on prose a stem inside a word misleads ("contractor" is not a
    # tractor, "translational" is not translation), so a hit must start a word here
    starts = lambda rx, t: sum(1 for m in rx.finditer(t) if m.start() == 0 or not t[m.start() - 1].isalpha())  # noqa: E731
    for sec, rx in _KW:
        score[sec] += 2 * starts(rx, lead_t) + starts(rx, prod_t)
    ranked = sorted(((v, k) for k, v in score.items() if v > 0), reverse=True)
    if not ranked or ranked[0][0] < 2:
        return "", "unclear (too few product words)", ranked[0][0] if ranked else 0
    if len(ranked) > 1 and ranked[0][0] < 1.5 * ranked[1][0]:
        return "", f"unclear ({SECTORS.get(ranked[0][1], ranked[0][1])} vs {SECTORS.get(ranked[1][1], ranked[1][1])})", ranked[0][0]
    return ranked[0][1], "site text", ranked[0][0]


BOTWALL = re.compile(r"pardon our interruption|made us think you were a bot|are you a robot|checking your browser|"
                     r"attention required|cf-browser-verification|access denied|request unsuccessful|captcha", re.I)
CSSLIKE = re.compile(r"@font-face|font-family|\{[^}]*:[^}]*;|var\(--|function\s*\(|=>")


def analyse(name, record_sector, pages):
    """pages: [(url, html)] of one site, home first. Returns the check fields (pure: no network)."""
    home_url, home = pages[0]
    texts = [text_of(p) for _, p in pages]
    alltext = "\n".join(texts)
    title = title_of(home)
    desc = meta_description(home)
    if not desc:
        para = next((x.strip() for x in texts[0].split("\n") if 80 <= len(x.strip()) <= 600 and not EMAIL.search(x) and not CSSLIKE.search(x)), "")
        desc = para
    domain = site_domain(home_url)
    nm, share = name_match(name, title, alltext)
    prods = []
    for _, p in pages:
        prods += [h for h in headings(p) if h not in prods]
    sec, how, sec_score = site_sector(f"{title}. {desc}", prods)
    roles = []
    role_text = "\n".join([title, desc] + [text_of(p) for u, p in pages if ROLE_PAGE.search(urlsplit(u).path or "/")])
    for role, rx in ROLE_RULES:
        m = rx.search(role_text)
        if m:
            roles.append({"role": role, "phrase": m.group(0)[:80]})
    certs = sorted({re.sub(r"\s+", " ", m.group(0)).upper().replace("ISO9", "ISO 9").replace("ISO1", "ISO 1").replace("ISO2", "ISO 2").replace("ISO4", "ISO 4")
                    for m in CERTS.finditer(alltext)})[:15]
    exp = EXPORT.search(alltext)
    near = " ".join(l for l in alltext.split("\n") if EXPORT.search(l))[:3000] if exp else ""
    named_countries = sorted({iso for iso, rx in COUNTRIES if rx.search(near)}) if near else []
    if len(named_countries) > 40:  # a list of every country is a site's country picker, not export evidence
        named_countries = []
    ids = []
    for kind, rx in LEGAL_ID:
        for m in rx.finditer(alltext):
            v = m.group(1).strip()
            if v not in (x["value"] for x in ids):
                ids.append({"kind": kind, "value": v})
    phones = list(dict.fromkeys(p.strip() for p in PHONE.findall(alltext)))[:4]
    mails = emails_on(" ".join(p for _, p in pages), domain)
    linkedin, whatsapp = social_on([p for _, p in pages])
    org, ld_prods = structured_on([p for _, p in pages])
    if not linkedin:
        linkedin = next((u for u in org.get("same_as", []) if LINKEDIN.match(u)), "")
        if linkedin:
            m = LINKEDIN.match(linkedin); linkedin = f"https://www.linkedin.com/{m.group(1).lower()}/{m.group(2)}"
    if ld_prods:  # the site's own product records first, then headings
        prods = ld_prods + [p for p in prods if p not in ld_prods]
    from .validate import lei_ok
    if org.get("lei") and not lei_ok(org["lei"]):
        org.pop("lei")  # fails the ISO 17442 check digits: not an LEI
    for kind, v in (("VAT", org.get("vat")), ("LEI", org.get("lei")), ("DUNS", org.get("duns")), ("Tax id", org.get("tax_id"))):
        if v and v not in (x["value"] for x in ids):
            ids.append({"kind": kind, "value": v, "basis": "structured data"})
    gaps = []
    if nm == "none":
        gaps.append("the site does not name the company")
    if not mails:
        gaps.append("no e-mail on the company's own domain")
    if not prods and not desc:
        gaps.append("no product or description text")
    if not roles:
        gaps.append("role not stated (maker, trader, contractor)")
    rec_id = next((k for k, v in SECTORS.items() if v == record_sector), "") if record_sector else ""
    conflict = bool(sec and rec_id and sec != rec_id)
    return {
        "title": title, "description": desc[:500], "products": prods[:30], "domain": domain, "name_match": nm, "name_share": share,
        "sector": SECTORS.get(sec, "") if sec else "", "sector_basis": how, "sector_score": sec_score, "sector_conflict": conflict,
        "record_sector": record_sector or "", "roles": roles, "certificates": certs, "export_wording": exp.group(0) if exp else "",
        "export_countries": named_countries, "legal_ids": ids[:8], "phones": phones, "emails": mails, "linkedin": linkedin, "whatsapp": whatsapp, "structured": org, "products_basis": "structured data and headings" if ld_prods else "headings", "gaps": gaps,
        "verdict": "name mismatch" if nm == "none" else "ok",
    }


# ---------------------------------------------------------------- network (polite)
def _session():
    import requests
    s = requests.Session(); s.headers["User-Agent"] = UA; s.headers["Accept-Language"] = "en,*;q=0.5"
    return s


def _get(s, url):
    try:
        r = s.get(url, timeout=10, allow_redirects=True, stream=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            r.close(); return None, r.status_code
        body = r.raw.read(PAGE_BYTES, decode_content=True)
        r.close()
        declared = re.search(r"charset=([\w-]+)", r.headers.get("content-type", ""), re.I)
        meta = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4000], re.I)
        enc = (declared.group(1) if declared else meta.group(1).decode() if meta else "utf-8")
        try:
            txt = body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            try:
                txt = body.decode("utf-8")
            except UnicodeDecodeError:
                txt = body.decode("latin-1", errors="replace")
        return (r.url, txt), 200
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def links(base, page):
    out = []
    host = site_domain(base)
    for m in re.finditer(r'<a[^>]+href=["\']([^"\'#]+)["\']', page, re.I):
        u = urljoin(base, m.group(1).strip())
        if not u.startswith("http") or site_domain(u) != host or re.search(r"\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?|mp4)$|login|cart|account|wp-admin|mailto:|tel:", u, re.I):
            continue
        if LINK_HINT.search(urlsplit(u).path) and u not in out:
            out.append(u)
    # about and products before contact; shorter paths first
    rank = lambda u: (0 if re.search(r"about|company|empresa|profile|unternehmen", u, re.I) else 1 if re.search(r"produc|solution|range|catalog", u, re.I) else 2, len(u))  # noqa: E731
    return sorted(out, key=rank)


def fetch_site(url):
    """[(url, html)] for up to MAX_PAGES pages of the site, or (None, reason)."""
    if not url.startswith("http"):
        url = "http://" + url.strip().strip("/")
    s = _session()
    first, code = _get(s, url)
    if not first and url.startswith("http://"):
        first, code = _get(s, "https://" + url[7:])
    if not first:
        return None, f"unreachable ({code})"
    final, home = first
    base = "{0.scheme}://{0.netloc}/".format(urlsplit(final))
    rp = RobotFileParser()
    rr, _ = _get(s, urljoin(base, "robots.txt"))
    rp.parse(rr[1].splitlines() if rr else [])
    if not rp.can_fetch(UA, base):
        return None, "blocked by robots.txt"
    if PARKED.search(text_of(home)[:6000]):
        return None, "parked or placeholder page"
    if BOTWALL.search(text_of(home)[:4000]) and len(text_of(home)) < 6000:
        return None, "blocked by bot protection"
    pages = [(final, home)]
    for u in links(base, home):
        if len(pages) >= MAX_PAGES:
            break
        if not rp.can_fetch(UA, u):
            continue
        time.sleep(0.6)  # one host, one request at a time
        got, _ = _get(s, u)
        if got:
            pages.append(got)
    return pages, ""


# ---------------------------------------------------------------- queue and storage
def load_checks():
    out = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line); out[d["key"]] = d
            except (ValueError, KeyError):
                pass
    return out


def _sheet_rows(sid, rng):
    try:
        from .push import Sheets
        return Sheets().values(sid, rng)
    except (Exception, SystemExit) as e:  # noqa: BLE001  no credentials locally, or the tab does not exist yet
        log.info("company check: %s not read (%s)", rng, str(e)[:80])
        return []


def queue(rows, checks, limit, today):
    """Ordered (key, name, country, website, record_sector, reason) to check now."""
    by_key = {f"{r['supplier']}|{r['country']}": r for r in rows}
    by_name = defaultdict(list)
    for r in rows:
        by_name[r["supplier"].strip().lower()].append(r)
    stale = (today - timedelta(days=RECHECK_DAYS)).isoformat()
    # due: never checked, checked before the recheck window, or checked by an older version of these rules
    due = lambda k: k not in checks or str(checks[k].get("checked", "")) < stale or checks[k].get("version") != VERSION  # noqa: E731
    picked, seen = [], set()

    def add(r, reason, force=False, discover=False):
        k = f"{r['supplier']}|{r['country']}"
        if k in seen or (not force and not due(k)):
            return
        w = (r.get("website") or "").strip()
        if not w:
            em = (r.get("email") or "").split(";")[0].strip()
            if "@" in em and not re.search(r"@(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|qq|163|126)\.", em, re.I):
                w = em.split("@")[1]
        if not w and not discover:
            return
        # no site at all: the check first looks for one (likely domains, accepted only when the page names the company)
        seen.add(k); picked.append((k, r["supplier"], r["country"], w, r.get("main_sector", ""), reason))

    # 1. asked from the panel (Check queue: time, company, country, by)
    from .push import LEADS_SHEET
    STATE_SHEET = "1LrpaLYWZp3OJfMF8aNtNQM6JByy4QpQU-PAKuE_VVVo"  # the app's state sheet (Activity and other logs)
    for q in _sheet_rows(LEADS_SHEET, "'Check queue'!A2:D2000")[-300:]:
        q = q + [""] * 4
        for r in ([by_key[f"{q[1]}|{q[2]}"]] if f"{q[1]}|{q[2]}" in by_key else by_name.get(q[1].strip().lower(), [])[:2]):
            add(r, "asked in the panel", force=True)
    # 2. supplier pages opened in the last 30 days (Activity: time, email, name, role, action, target, detail;
    # an opened supplier is action "open", target "company <name>", detail "<name> | sector | country")
    since = (today - timedelta(days=30)).isoformat()
    # the app's Activity log lives in the state sheet since 9 Nov 2026 (the engine copy is the older history)
    acts = _sheet_rows(LEADS_SHEET, "'Activity'!A2:G50000")
    try:
        acts = acts + _sheet_rows(STATE_SHEET, "'Activity'!A2:G50000")
    except Exception:
        pass
    for a in acts[-10000:]:
        a = a + [""] * 7
        if str(a[0])[:10] < since or a[4] != "open" or not str(a[5]).startswith("company "):
            continue
        name = str(a[5])[8:].strip().lower()
        cty = (str(a[6]).split(" | ") + ["", "", ""])[2].strip()
        cands = by_name.get(name, [])
        for r in ([x for x in cands if x["country"] == cty] or cands)[:2]:
            add(r, "opened in the panel")
    # 2a. refresh: sites read correctly more than RECHECK_DAYS ago (oldest first, at most a quarter of a run), so a
    # site that went down or changed its phones and mailboxes is caught
    old = sorted((c.get("checked", ""), k) for k, c in checks.items() if c.get("verdict") == "ok" and str(c.get("checked", "")) < stale)
    for _, k in old[: limit // 4]:
        if k in by_key:
            add(by_key[k], f"refresh: last read {checks[k].get('checked')}")
    # 2b. what the refinement asked for (leads/refine.py check_queue: proven suppliers first, then sites on record)
    rq = CHECKS / "refine" / "check_queue.txt"
    if rq.exists():
        n_disc = 0
        for k in rq.read_text(encoding="utf-8").splitlines()[: limit * 2]:
            r = by_key.get(k)
            if not r:
                continue
            nosite = not (r.get("website") or r.get("email"))
            if nosite and n_disc >= limit // 3:  # discovery is slower: at most a third of a run
                continue
            n_disc += nosite
            add(r, "refinement: " + ("find the official website" if nosite else "confirm the website on record"), discover=nosite)
    # 2c. companies known only by a Chinese name (imported directories): a tenth of each run looks for their site in
    # pinyin (Fortune China 500 first), since the generic queue would reach them only after every proven supplier
    from .zh_names import is_cjk
    zh = [r for r in rows if not (r.get("website") or "").strip() and is_cjk(r.get("supplier", "")) and due(f"{r['supplier']}|{r['country']}")]
    zh.sort(key=lambda r: ("Fortune" not in (r.get("sources") or ""), r.get("supplier", "")))
    for r in zh[: limit // 10]:
        add(r, "Chinese name: find the official website", discover=True)
    # 3. proven suppliers with an unknown or flagged sector; 4. proven, never checked; 5. the rest, best first
    proven = [r for r in rows if r.get("tier") in ("1", "2")]
    for r in proven:
        if not r.get("main_sector") or r.get("sector_check"):
            add(r, "sector unknown or flagged")
    for r in proven:
        add(r, "proven, not checked")
    for r in rows:
        if len(picked) >= limit * 2:
            break
        add(r, "recheck or remaining")
    return picked[:limit]


def push_sheet(checks):
    """Latest check per company into the private sheet tab 'Company checks' for the panel (best first)."""
    try:
        from .push import UNIVERSE_SHEET, Sheets
    except Exception:  # noqa: BLE001
        return
    head = ["key", "supplier", "country", "checked", "verdict", "name_match", "website", "domain", "description", "products", "sector",
            "record_sector", "sector_conflict", "roles", "certificates", "export", "export_countries", "legal_ids", "emails", "phones", "gaps",
            "reason", "version", "content_hash", "linkedin", "whatsapp", "changes", "structured"]
    rows = [head]
    for c in sorted(checks.values(), key=lambda c: c.get("checked", ""), reverse=True)[:30000]:
        rows.append([c.get("key", ""), c.get("supplier", ""), c.get("country", ""), c.get("checked", ""), c.get("verdict", ""), c.get("name_match", ""),
                     c.get("website", ""), c.get("domain", ""), c.get("description", "")[:300], "; ".join(c.get("products", [])[:12])[:400], c.get("sector", ""),
                     c.get("record_sector", ""), "yes" if c.get("sector_conflict") else "", "; ".join(f"{x['role']}: {x['phrase']}" for x in c.get("roles", []))[:300],
                     "; ".join(c.get("certificates", [])), c.get("export_wording", ""), " ".join(c.get("export_countries", [])),
                     "; ".join(f"{x['kind']} {x['value']}" for x in c.get("legal_ids", [])), "; ".join(f"{x['email']} ({x['kind']})" for x in c.get("emails", [])),
                     "; ".join(c.get("phones", [])), "; ".join(c.get("gaps", [])), c.get("reason", ""), c.get("version", ""), c.get("content_hash", ""),
                     c.get("linkedin", ""), " ".join(c.get("whatsapp", [])), "; ".join(c.get("changes") or [])[:300],
                     "; ".join(f"{k}: {v}" for k, v in (c.get("structured") or {}).items() if k != "same_as")[:400]])
    try:
        Sheets().replace_tab(UNIVERSE_SHEET, "Company checks", rows, raw=True)
        log.info("company checks: %d rows written to the sheet", len(rows) - 1)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        log.warning("company checks: sheet not written (%s)", str(e)[:120])


def check_one(item, prev):
    key, name, country, website, rec_sector, reason = item
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    base = {"key": key, "supplier": name, "country": country, "website": website, "checked": now[:10], "checked_at": now,
            "reason": reason, "version": VERSION, "record_sector": rec_sector}
    if not website:
        try:
            from .web_contacts import discover, discover_zh
            from .zh_names import is_cjk
            website = (discover_zh(name) if is_cjk(name) else discover(name, country)) or ""
        except Exception:  # noqa: BLE001
            website = ""
        base["website"] = website
        if not website:
            return {**base, "verdict": "no website found", "detail": "likely domains tried; none names the company", "gaps": ["no website found"], "content_hash": ""}
        base["discovered"] = True
    pages, why = fetch_site(website)
    if not pages:
        out = {**base, "verdict": why.split(" (")[0], "detail": why, "gaps": [why], "content_hash": ""}
        if prev and prev.get("verdict") == "ok":  # it worked before: keep what it said, and say since when it is down
            out["last_good"] = {k: prev.get(k) for k in ("checked", "website", "emails", "phones", "linkedin", "whatsapp") if prev.get(k)}
            out["changes"] = [f"site {why.split(' (')[0]} (it was read on {prev.get('checked')})"]
        return out
    h = hashlib.sha1("".join(text_of(p)[:20000] for _, p in pages).encode("utf-8", "ignore")).hexdigest()[:16]
    if prev and prev.get("content_hash") == h and prev.get("version") == VERSION:
        return {**prev, "checked": now[:10], "checked_at": now, "reason": reason, "unchanged": True, "changes": []}
    res = analyse(name, rec_sector, pages)
    res["changes"] = changes(prev, res) if prev and prev.get("verdict") == "ok" else []
    return {**base, **res, "website": pages[0][0], "pages": [u for u, _ in pages], "content_hash": h}


def changes(prev, cur):
    """What changed on a site since its last good read: contact channels and products (pure)."""
    out = []
    em = lambda c: {x["email"] for x in c.get("emails") or []}  # noqa: E731
    for label, a, b in (("e-mails", em(prev), em(cur)), ("phones", set(prev.get("phones") or []), set(cur.get("phones") or [])),
                        ("WhatsApp", set(prev.get("whatsapp") or []), set(cur.get("whatsapp") or []))):
        if a - b:
            out.append(f"{label} removed: {', '.join(sorted(a - b))[:120]}")
        if b - a and a:
            out.append(f"{label} added: {', '.join(sorted(b - a))[:120]}")
    if prev.get("linkedin") and cur.get("linkedin") and prev["linkedin"] != cur["linkedin"]:
        out.append(f"LinkedIn changed: {cur['linkedin']}")
    pa, pb = set(prev.get("products") or []), set(cur.get("products") or [])
    if pa and pb and len(pa & pb) < 0.5 * min(len(pa), len(pb)):
        out.append("products changed (most product headings are new)")
    if prev.get("website") and cur.get("domain") and site_domain(prev["website"]) != cur["domain"]:
        out.append(f"website moved: {site_domain(prev['website'])} -> {cur['domain']}")
    return out[:6]


def main(limit=1500, minutes=45):
    src = PRIVATE / "universe.csv"
    if not src.exists():
        log.info("company check: no universe yet"); return {}
    CHECKS.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    checks = load_checks()
    today = date.today()
    todo = queue(rows, checks, limit, today)
    deadline = time.time() + minutes * 60
    stats = defaultdict(int)
    # many companies in parallel; inside one company the pages are fetched one after another with a pause
    with ThreadPoolExecutor(max_workers=96) as ex, open(OUT, "a", encoding="utf-8") as f:
        futs = []
        for item in todo:
            futs.append((item, ex.submit(lambda it: None if time.time() > deadline else check_one(it, checks.get(it[0])), item)))
        for item, fu in futs:
            try:
                res = fu.result(timeout=max(1, deadline - time.time() + 60))
            except Exception:  # noqa: BLE001
                res = None
            if not res:
                continue
            checks[res["key"]] = res
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            stats[res.get("verdict", "?")] += 1
            stats["unchanged"] += 1 if res.get("unchanged") else 0
            stats["sector_conflict"] += 1 if res.get("sector_conflict") else 0
    # keep the file to one line per company (latest)
    OUT.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in checks.values()), encoding="utf-8")
    push_sheet(checks)
    log.info("company check: %d queued, %s, %d companies on record", len(todo), dict(stats), len(checks))
    return {"queued": len(todo), **stats, "on_record": len(checks)}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    a = sys.argv[1:]
    lim = int(a[a.index("--limit") + 1]) if "--limit" in a else 4000
    mins = int(a[a.index("--minutes") + 1]) if "--minutes" in a else 40
    print(main(lim, mins))
