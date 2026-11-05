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
VERSION = "check-2"
RECHECK_DAYS = 90
MAX_PAGES = 6
PAGE_BYTES = 600_000

LEGAL = re.compile(r"\b(s\.?a\.?s?|ltda|ltd|limited|llc|inc|gmbh|ag|kg|srl|s\.?r\.?l|spa|s\.?p\.?a|bv|nv|plc|pty|cc|co|corp|"
                   r"corporation|company|group|holding|sarl|sa de cv|de cv|cia|eirl|sac|oy|ab|as|a/s|kft|zrt|sp z o o|"
                   r"jsc|ojsc|pjsc|ooo|tov|llp|pvt|private|public|enterprises?|international|industries|trading|the|and|of|et|y|e)\b", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GENERIC = re.compile(r"^(info|sales|export|exports|contact|contacto|contato|kontakt|office|trade|trading|commercial|comercial|"
                     r"vendas|ventas|enquiries|inquiries|hello|marketing|orders|business|bd|procurement|tender|tenders|admin|"
                     r"mail|general|customerservice|service|support|ventes|vertrieb|verkauf)\b", re.I)
PHONE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,18}\d")
PARKED = re.compile(r"domain (is )?for sale|buy this domain|this domain (may be|is) for sale|parked (free|domain)|sedo\.com|"
                    r"hugedomains|dan\.com|coming soon|under construction|account (has been )?suspended|index of /|"
                    r"website is (currently )?(under|being)|default web site page|welcome to nginx|it works!", re.I)
LINK_HINT = re.compile(r"about|company|who-we-are|quienes|empresa|nosotros|sobre|unternehmen|societe|chi-siamo|profile|"
                       r"product|products|productos|produtos|produits|produkte|solutions|services|catalog|catalogue|range|"
                       r"contact|contacto|contato|kontakt|impressum|export|certific|quality|calidad|qualidade", re.I)
ROLE_RULES = [
    ("manufacturer", re.compile(r"\b(we (manufacture|produce|make)|manufacturer of|leading manufacturer|producer of|our (factory|plant|mill|production (line|facility|plant)s?)|"
                                r"production capacity|manufacturing (facility|plant|site)|fabricante|fabricamos|fabricação|fabrique|fabricant|hersteller|"
                                r"produzent|produttore|ISO 9001 certified (factory|plant)|tonnes per (year|day|annum)|tons per (year|day))\b", re.I)),
    # exporting is not trading: a manufacturer exports too, so export wording is recorded apart (EXPORT)
    ("trader", re.compile(r"\b(distributor (of|for)|trading company|we (distribute|import|resell)|importer (of|and)|wholesale(r|rs)?|"
                          r"authori[sz]ed (dealer|distributor|agent)|sole agent|representative of|distribuidor|importador|"
                          r"comercializadora|négoce|distributeur|großhandel|händler)\b", re.I)),
    ("epc", re.compile(r"\b(epc|turnkey|engineering,? procurement and construction|general contractor|main contractor|design and build|"
                       r"installation (and|&) commissioning|contratista|empreiteira|entreprise générale)\b", re.I)),
    ("service", re.compile(r"\b(consulting|consultancy|advisory|training|maintenance services|cleaning services|security services|"
                           r"staffing|recruitment|software development|it services|marketing agency|law firm|accounting)\b", re.I)),
]
CERTS = re.compile(r"\b(ISO\s?9001|ISO\s?14001|ISO\s?45001|OHSAS\s?18001|ISO\s?22000|ISO\s?13485|ISO\s?27001|ISO\s?50001|IATF\s?16949|"
                   r"AS\s?9100|FSSC\s?22000|HACCP|GMP|BRC(GS)?|IFS Food|CE mark(ing)?|CE certified|API\s?(5L|6D|Q1|spec)|ASME|PED|"
                   r"UL (listed|certified)|IECEx|ATEX|halal|kosher|organic certified|USDA organic|GOST|SASO|BIS|INMETRO|NSF|WRAS|DVGW|KEMA)\b", re.I)
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
        if k in seen or re.fullmatch(r"(home|about( us)?|contact( us)?|news|blog|careers?|login|menu|search|products?|services?|solutions?|read more|learn more)", k):
            continue
        seen.add(k); res.append(t)
    return res[:40]


def name_match(name, title, text):
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
        if core and (d == domain or d.endswith("." + domain) or core_of(d) == core):
            out.append({"email": e, "kind": "generic" if GENERIC.match(e.split("@")[0]) else "named"})
    return out[:6]


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
    for role, rx in ROLE_RULES:
        m = rx.search(alltext)
        if m:
            roles.append({"role": role, "phrase": m.group(0)[:80]})
    certs = sorted({re.sub(r"\s+", " ", m.group(0)).upper().replace("ISO9", "ISO 9").replace("ISO1", "ISO 1").replace("ISO2", "ISO 2").replace("ISO4", "ISO 4")
                    for m in CERTS.finditer(alltext)})[:15]
    exp = EXPORT.search(alltext)
    named_countries = sorted({iso for iso, rx in COUNTRIES if rx.search(alltext)})[:40] if exp else []
    ids = []
    for kind, rx in LEGAL_ID:
        for m in rx.finditer(alltext):
            v = m.group(1).strip()
            if v not in (x["value"] for x in ids):
                ids.append({"kind": kind, "value": v})
    phones = list(dict.fromkeys(p.strip() for p in PHONE.findall(alltext)))[:4]
    mails = emails_on(" ".join(p for _, p in pages), domain)
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
        "export_countries": named_countries, "legal_ids": ids[:6], "phones": phones, "emails": mails, "gaps": gaps,
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
        enc = r.encoding or "utf-8"
        return (r.url, body.decode(enc, errors="replace")), 200
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
    for q in _sheet_rows(LEADS_SHEET, "'Check queue'!A2:D2000")[-300:]:
        q = q + [""] * 4
        for r in ([by_key[f"{q[1]}|{q[2]}"]] if f"{q[1]}|{q[2]}" in by_key else by_name.get(q[1].strip().lower(), [])[:2]):
            add(r, "asked in the panel", force=True)
    # 2. supplier pages opened in the last 30 days (Activity: time, email, name, role, action, target, detail;
    # an opened supplier is action "open", target "company <name>", detail "<name> | sector | country")
    since = (today - timedelta(days=30)).isoformat()
    for a in _sheet_rows(LEADS_SHEET, "'Activity'!A2:G50000")[-10000:]:
        a = a + [""] * 7
        if str(a[0])[:10] < since or a[4] != "open" or not str(a[5]).startswith("company "):
            continue
        name = str(a[5])[8:].strip().lower()
        cty = (str(a[6]).split(" | ") + ["", "", ""])[2].strip()
        cands = by_name.get(name, [])
        for r in ([x for x in cands if x["country"] == cty] or cands)[:2]:
            add(r, "opened in the panel")
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
            "reason", "version", "content_hash"]
    rows = [head]
    for c in sorted(checks.values(), key=lambda c: c.get("checked", ""), reverse=True)[:30000]:
        rows.append([c.get("key", ""), c.get("supplier", ""), c.get("country", ""), c.get("checked", ""), c.get("verdict", ""), c.get("name_match", ""),
                     c.get("website", ""), c.get("domain", ""), c.get("description", "")[:300], "; ".join(c.get("products", [])[:12])[:400], c.get("sector", ""),
                     c.get("record_sector", ""), "yes" if c.get("sector_conflict") else "", "; ".join(f"{x['role']}: {x['phrase']}" for x in c.get("roles", []))[:300],
                     "; ".join(c.get("certificates", [])), c.get("export_wording", ""), " ".join(c.get("export_countries", [])),
                     "; ".join(f"{x['kind']} {x['value']}" for x in c.get("legal_ids", [])), "; ".join(f"{x['email']} ({x['kind']})" for x in c.get("emails", [])),
                     "; ".join(c.get("phones", [])), "; ".join(c.get("gaps", [])), c.get("reason", ""), c.get("version", ""), c.get("content_hash", "")])
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
            from .web_contacts import discover
            website = discover(name, country) or ""
        except Exception:  # noqa: BLE001
            website = ""
        base["website"] = website
        if not website:
            return {**base, "verdict": "no website found", "detail": "likely domains tried; none names the company", "gaps": ["no website found"], "content_hash": ""}
        base["discovered"] = True
    pages, why = fetch_site(website)
    if not pages:
        return {**base, "verdict": why.split(" (")[0], "detail": why, "gaps": [why], "content_hash": ""}
    h = hashlib.sha1("".join(text_of(p)[:20000] for _, p in pages).encode("utf-8", "ignore")).hexdigest()[:16]
    if prev and prev.get("content_hash") == h and prev.get("version") == VERSION:
        return {**prev, "checked": now[:10], "checked_at": now, "reason": reason, "unchanged": True}
    res = analyse(name, rec_sector, pages)
    return {**base, **res, "website": pages[0][0], "pages": [u for u, _ in pages], "content_hash": h}


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
    with ThreadPoolExecutor(max_workers=48) as ex, open(OUT, "a", encoding="utf-8") as f:
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
    lim = int(a[a.index("--limit") + 1]) if "--limit" in a else 400
    mins = int(a[a.index("--minutes") + 1]) if "--minutes" in a else 40
    print(main(lim, mins))
