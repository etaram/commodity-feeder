"""Company profile from the company's own public pages, in code (no model calls): the fields a buyer asks for first.

Pure extraction (no network), called by leads/company_check.analyse on the pages it already read:
  wechat        WeChat ids the site prints next to a WeChat / 微信 label, links to weixin.qq.com / u.wechat.com,
                and QR-code images the site labels WeChat (image URL kept; leads/enrich_server.py decodes it offline)
  whatsapp      numbers the site itself presents as WhatsApp (wa.me links, or a number printed after a WhatsApp
                label), each with its click-to-chat link https://wa.me/<digits>
  people        role holders the site publishes (team / about / leadership / contact pages, schema.org Person):
                name, title, the page, and a LinkedIn profile only when the site links it next to that person.
                Only business roles (chief executive, managing director, founder, owner, sales / export, procurement,
                business development); no private data
  founded       founding year (schema.org foundingDate, "founded in / established in / since / 成立于 ...")
  employees     the employee count the site states, and its phrase
  revenue       turnover / revenue the site states, with currency and the phrase (never estimated)
  capacity      production capacity and plant area the site states (size signals for producers)
  size          small / mid / large with its basis (employees first, then revenue); "not stated" otherwise
  summary       a short factual summary assembled from the fields above and the site's own description; every part
                comes from the gathered text, missing parts are left out, nothing is inferred

Network helpers used by the server job only (leads/enrich_server.py): press articles from Google News RSS (exact name,
country-checked), Wikidata facts for notable companies (only when the entity's official website is this domain),
public search-result snippets for linkedin.com/in that name the company and a title (rate-limited, stops when the
engine pushes back; no login, no CAPTCHA), and offline QR decoding (OpenCV, when installed).
"""
import html
import json
import re
from datetime import date
from urllib.parse import quote, urljoin, urlsplit

PROFILE_VERSION = "profile-1"
TAG = re.compile(r"<[^>]+>")
STRIP = re.compile(r"<(script|style|noscript|svg|template)[^>]*>.*?</\1>", re.I | re.S)


def _text(page):
    t = STRIP.sub(" ", page)
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</div>|</td>|</tr>|</span>|</a>", "\n", t, flags=re.I)
    t = html.unescape(TAG.sub(" ", t))
    return re.sub(r"[ \t\r\f\v\xa0]+", " ", t)


# ---------------------------------------------------------------- WeChat
WECHAT_LABEL = r"(?:we\s?chat|weixin|微信)"
WECHAT_ID = re.compile(WECHAT_LABEL + r"\s*(?:id|号|號|account)?\s*[:：]\s*\+?([A-Za-z][-_A-Za-z0-9]{5,19}|\d[\d\s-]{7,16}\d)", re.I)
WECHAT_LINK = re.compile(r"https?://(?:weixin\.qq\.com/r/[A-Za-z0-9_-]{6,40}|u\.wechat\.com/[A-Za-z0-9_-]{6,60}|open\.weixin\.qq\.com/qr/code\?username=[A-Za-z0-9_-]{4,40})", re.I)
IMG = re.compile(r"<img\b[^>]*>", re.I)
ATTR = lambda a: re.compile(a + r"""\s*=\s*["']([^"']{1,400})["']""", re.I)  # noqa: E731
SRC, ALT, CLS, TITLE_A, DSRC = ATTR("src"), ATTR("alt"), ATTR("class"), ATTR("title"), ATTR("data-(?:src|lazy-src|original)")


def wechat_on(pages):
    """[(url, html)] -> {"ids": [..], "links": [..], "qr_images": [..]}: only what the site itself labels WeChat."""
    ids, links, qrs = [], [], []
    for url, page in pages:
        t = _text(page)
        for m in WECHAT_ID.finditer(t):
            v = re.sub(r"[\s-]", "", m.group(1)) if m.group(1)[0].isdigit() else m.group(1)
            if v.lower() in ("official", "account", "scan", "follow", "public", "qrcode") or v in ids:
                continue
            ids.append(v)
        for m in WECHAT_LINK.finditer(page):
            if m.group(0) not in links:
                links.append(m.group(0))
        for m in IMG.finditer(page):
            tag = m.group(0)
            src = (DSRC.search(tag) or SRC.search(tag))
            if not src:
                continue
            s = src.group(1).strip()
            label = " ".join(x.group(1) for x in (ALT.search(tag), CLS.search(tag), TITLE_A.search(tag)) if x)
            ctx = _text(page[max(0, m.start() - 300): m.end() + 300])
            # the image itself is labelled WeChat, or it is a QR image next to a WeChat label
            is_wx = re.search(WECHAT_LABEL, s + " " + label, re.I) or (
                re.search(r"qr|二维码|code", s + " " + label, re.I) and re.search(WECHAT_LABEL, ctx, re.I))
            if is_wx and not s.startswith("data:") and not re.search(r"icon|logo|sprite|share", s + " " + label, re.I):
                u = urljoin(url, s)
                if u not in qrs:
                    qrs.append(u)
    return {"ids": ids[:3], "links": links[:3], "qr_images": qrs[:3]}


WEIXIN_URL = re.compile(r"^(https?://(weixin\.qq\.com|u\.wechat\.com|wechat\.com|open\.weixin\.qq\.com|work\.weixin\.qq\.com)/|wxp://)", re.I)


def decode_qr(img_bytes):
    """Offline QR decode (OpenCV, if installed). Returns the text only when it is a WeChat URL, else ""."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return ""
    try:
        a = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if a is None:
            return ""
        txt, _, _ = cv2.QRCodeDetector().detectAndDecode(a)
    except Exception:  # noqa: BLE001
        return ""
    return txt if txt and WEIXIN_URL.match(txt) else ""


# ---------------------------------------------------------------- WhatsApp
WA_LABEL = re.compile(r"(?:whats\s?app|ватсап|واتساب|واتس اب)\s*(?:no\.?|number|nr\.?|#)?\s*[:：]?\s*((?:\+|00)?\d[\d\s().-]{7,18}\d)", re.I)


def whatsapp_on(pages, linked, country=""):
    """Numbers the site presents as WhatsApp: the wa.me / api.whatsapp.com links company_check.social_on found
    (`linked`, +digits) and numbers printed right after a WhatsApp label. Returns [{"number", "link", "basis"}]."""
    out = []

    def add(num, basis):
        d = re.sub(r"\D", "", num)
        if num.strip().startswith("00"):
            d = d[2:]
        elif not num.strip().startswith("+") and country:
            d = _with_cc(d, country)
            if not d:
                return
        if not (8 <= len(d) <= 15) or re.fullmatch(r"(\d)\1+", d):
            return
        if not _valid(d):
            # a wa.me link written with the national number only (no country code): rebuilt for the company's country
            d = _with_cc(d, country) if country else ""
            if not d:
                return
            basis += " (country code added)"
        if any(x["number"] == "+" + d for x in out):
            return
        out.append({"number": "+" + d, "link": f"https://wa.me/{d}", "basis": basis})

    for n in linked or []:
        add(n, "click-to-chat link on the site")
    for _, page in pages:
        for m in WA_LABEL.finditer(_text(page)):
            add(m.group(1), "printed after a WhatsApp label on the site")
    return out[:3]


def _valid(d):
    try:
        import phonenumbers
        return phonenumbers.is_valid_number(phonenumbers.parse("+" + d, None))
    except ImportError:
        return True
    except Exception:  # noqa: BLE001
        return False


def _with_cc(d, country):
    """A national number printed without +code: add the country's calling code (phonenumbers, when installed)."""
    try:
        import phonenumbers
        import pycountry
        c = pycountry.countries.get(alpha_3=country)
        p = phonenumbers.parse(d, c.alpha_2 if c else None)
        if phonenumbers.is_valid_number(p):
            return f"{p.country_code}{p.national_number}"
    except Exception:  # noqa: BLE001
        pass
    return ""


# ---------------------------------------------------------------- people by title
ROLE_TITLES = [
    ("chief executive", r"chief executive officer|\bCEO\b|managing director|\bM\.?D\.?\b(?= *[,|-])|general manager|\bGM\b|"
                        r"president(?! of the)|geschäftsführer(?:in)?|gerente general|director general|diretor(?:a)? (?:geral|presidente)|"
                        r"directeur général|PDG|amministratore delegato|direttore generale|总经理|總經理|首席执行官|executive director"),
    ("founder / owner", r"co-?founder|founder|owner|proprietor|propriétaire|fundador(?:a)?|gründer(?:in)?|inhaber(?:in)?|创始人|董事长|chairman|chairwoman|chairperson"),
    ("sales / export", r"(?:head of|director of|vp of|vice president,?|chief) (?:sales|export|exports|commercial|marketing and sales)|"
                       r"(?:sales|export|exports|commercial|international sales|international business|overseas sales|marketing (?:and|&) sales) (?:director|manager|head|lead|executive)|"
                       r"\bCCO\b|chief commercial officer|director comercial|gerente comercial|gerente de (?:ventas|exportaci[oó]n)|diretor(?:a)? comercial|"
                       r"directeur commercial|directeur export|export manager|vertriebsleiter(?:in)?|exportleiter(?:in)?|销售经理|销售总监|外贸经理|国际贸易部经理"),
    ("procurement", r"(?:head of|director of|chief) (?:procurement|purchasing|supply chain|sourcing)|(?:procurement|purchasing|sourcing|supply chain) (?:director|manager|head|lead)|"
                    r"\bCPO\b|chief procurement officer|jefe de compras|gerente de compras|einkaufsleiter(?:in)?|采购经理"),
    ("business development", r"business development (?:director|manager|head|lead|executive)|(?:head|director|vp) of business development|\bBDM\b|"
                             r"desarrollo de negocios|développement commercial|商务拓展|业务拓展"),
]
ROLE_RX = [(k, re.compile(rx, re.I)) for k, rx in ROLE_TITLES]
ANY_ROLE = re.compile("|".join(f"(?:{rx})" for _, rx in ROLE_TITLES), re.I)
NAME_WORD = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{1,20}"
LATIN_NAME = re.compile(rf"^(?:(?:Mr|Mrs|Ms|Dr|Eng|Ing|Prof)\.?\s+)?({NAME_WORD}(?:\s+(?:[A-Z]\.|{NAME_WORD}|(?:van|von|de|da|del|di|dos|der|bin|al|el|la)\b)){{1,3}})$")
CJK_NAME = re.compile(r"^[一-鿿]{2,4}$")
NOT_NAME = re.compile(r"\b(company|group|limited|ltd|inc|gmbh|corp|industr|products?|solutions?|services?|team|contact|about|our|the|"
                      r"sales|export|manager|director|office|department|global|international|head|chief|officer|president|founder|"
                      r"chairman|member|board|management|leadership|executive|general|news|read|more|view|profile|email|phone|"
                      r"address|factory|quality|welcome|home|customer|support|market|business|development|purchasing|procurement|"
                      r"engineering|technology|production|operations|finance|human|resources|marketing|commercial|copyright|rights|"
                      r"reserved|privacy|policy|cookie|search|menu|street|road|avenue|china|india|turkey|brazil|germany|united|"
                      r"republic|kingdom|states|city|province|district|zone|park|building|floor|room|tel|fax|mobile|whatsapp|wechat|"
                      r"press|releases?|awards?|outstanding|entrepreneur|investors?|careers?|events?|media|download)\b", re.I)
# pages that quote other companies' people (customers, testimonials, case studies, news): no role holders taken there
NOT_PEOPLE_PAGE = re.compile(r"customer|client|testimonial|case-stud|reference|news|press|blog|award|event|partner|project", re.I)
NOT_TARGET = re.compile(r"non-?executive|independent (?:director|member)|board member|secretary|auditor|nominee", re.I)
PEOPLE_PAGE = re.compile(r"team|about|leadership|management|board|people|who-we-are|company|contact|direct|staff|founder|"
                         r"quienes|nosotros|equipo|equipe|unternehmen|ueber-uns|über-uns|impressum|imprint|关于|团队|联系", re.I)
LI_IN = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]{3,100})", re.I)


def _role_of(title):
    for k, rx in ROLE_RX:
        if rx.search(title):
            return k
    return ""


def _clean_name(s, cjk=False):
    s = re.sub(r"\s+", " ", s).strip(" ,.;:-|–—·•")
    if CJK_NAME.match(s):
        return s if cjk and not re.search(r"中文|英文|简介|介绍|联系|役員|会社|公司|首页|产品|新闻", s) else ""
    m = LATIN_NAME.match(s)
    if not m or NOT_NAME.search(m.group(1)):
        return ""
    n = m.group(1)
    toks = n.split()
    # four capitalised words with no initial and no particle are two names run together ("Anna Kowalska Pedro Alvarez")
    if len(toks) >= 4 and not any(re.fullmatch(r"[A-Z]\.|van|von|de|da|del|di|dos|der|bin|al|el|la|Al|El|Bin|Abu|Abdul|Ul|Ur", t) for t in toks):
        return ""
    if n.isupper() or len(n) > 45:
        return ""
    return n


def people_on(pages):
    """[(url, html)] -> [{"name", "title", "role", "source", "linkedin"?, "basis"}]: business role holders the company's
    own site publishes. Strict: a person counts only as a clean personal name right next to a known role title."""
    found = []

    def add(name, title, url, basis, li="", cjk=False):
        name, title = _clean_name(name, cjk), re.sub(r"\s+", " ", title).strip(" ,.;:-|–—()")[:80]
        role = "" if NOT_TARGET.search(title) else _role_of(title)
        if not name or not role or any(p["name"].lower() == name.lower() for p in found):
            return
        p = {"name": name, "title": title, "role": role, "source": url, "basis": basis, "confidence": "own site"}
        if li:
            p["linkedin"] = li
        found.append(p)

    for url, page in pages:
        # schema.org Person records (the site's own structured statement)
        for m in re.finditer(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page, re.I | re.S):
            try:
                j = json.loads(html.unescape(m.group(1).strip()))
            except ValueError:
                continue
            stack = [j]
            while stack:
                x = stack.pop()
                if isinstance(x, list):
                    stack.extend(x[:50])
                elif isinstance(x, dict):
                    t = x.get("@type")
                    if (t == "Person" or (isinstance(t, list) and "Person" in t)) and x.get("name") and x.get("jobTitle"):
                        same = x.get("sameAs") or []
                        same = [same] if isinstance(same, str) else same
                        li = next((u for u in same if isinstance(u, str) and LI_IN.match(u)), "")
                        add(str(x["name"]), str(x["jobTitle"] if not isinstance(x["jobTitle"], list) else x["jobTitle"][0]), url, "schema.org Person on the site", li)
                    for k in ("@graph", "founder", "employee", "member", "author", "contactPoint", "itemListElement", "item"):
                        if k in x:
                            stack.append(x[k])
        path = urlsplit(url).path or "/"
        if (not PEOPLE_PAGE.search(path) and path not in ("", "/")) or NOT_PEOPLE_PAGE.search(path):
            continue
        # text blocks: "Name, Title" / "Name - Title" / "Title: Name" on one line, or a name line with the title next to it
        lines = [x.strip() for x in _text(page).split("\n") if x.strip()]
        for i, line in enumerate(lines[:4000]):
            if len(line) > 140 or not ANY_ROLE.search(line):
                continue
            m = re.match(r"^(.{3,45}?)\s*(?:,|\s[-–—|]\s|:)\s*(.{2,80})$", line)
            if m and ANY_ROLE.search(m.group(2)) and not ANY_ROLE.search(m.group(1)):
                add(m.group(1), m.group(2), url, "name and title on one line")
                continue
            m = re.match(r"^(.{2,80}?)\s*[:：]\s*(.{2,45})$", line)
            if m and ANY_ROLE.fullmatch(m.group(1).strip()) and not ANY_ROLE.search(m.group(2)):
                add(m.group(2), m.group(1), url, "title and name on one line", cjk=True)
                continue
            if ANY_ROLE.fullmatch(line.strip(" ,.;:-|")) or (len(line) <= 60 and ANY_ROLE.search(line) and not re.search(r"[.!?]$", line)):
                for j in (i - 1, i + 1):  # a team card: the name on the line above (or below) the title
                    if j == i + 1 and i + 2 < len(lines) and ANY_ROLE.search(lines[i + 2]):
                        continue  # the line below is the next card's name, with its own title under it
                    if 0 <= j < len(lines) and not ANY_ROLE.search(lines[j]):
                        before = len(found)
                        add(lines[j], line, url, "team card (name next to title)")
                        if len(found) > before:
                            break
        # a LinkedIn profile linked inside the same card as the person's name
        for p in found:
            if p.get("linkedin") or p["source"] != url:
                continue
            i = page.find(p["name"])
            if i >= 0:
                win = page[max(0, i - 600): i + 900]
                lm = LI_IN.findall(win)
                if len(set(lm)) == 1:
                    p["linkedin"] = f"https://www.linkedin.com/in/{lm[0]}"
    return found[:12]


def linkedin_search_url(name, company):
    """A link that opens LinkedIn's own people search for this person at this company (nothing is fetched)."""
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote(f"{name} {company}"[:120])


# ---------------------------------------------------------------- size and age
THIS_YEAR = date.today().year
# strong wording (founded, established, incorporated) beats "since", which often dates a product line or a branch
FOUNDED = re.compile(r"(?<![\w])(?:founded|established|incorporated|set up|fundad[ao] (?:en|em)|fondée? en|gegründet|成立于|始建于|创建于|创立于|成立於)"
                     r"[ \t]*(?:in[ \t]+|on[ \t]+|en[ \t]+|em[ \t]+|im jahr[ \t]+)?(?:[A-Za-z]+[ \t]+(?:\d{1,2},?[ \t]+)?)?((?:18|19|20)\d\d)\b", re.I)
SINCE = re.compile(r"(?<![\w])(?:since|est\.|desde|depuis|seit)[ \t]+((?:18|19|20)\d\d)\b", re.I)
EMPLOYEES = re.compile(r"(?:(?:over|more than|about|around|approximately|nearly|almost|>)\s+)?(\d{1,3}(?:[,.\s]\d{3})*|\d+)\s*\+?\s*"
                       r"(?:employees|staff|workers|people|team members|professionals|colaboradores|empleados|funcionários|mitarbeiter(?:innen)?|salariés|名员工|员工|名职工)", re.I)
EMPLOYEES_ZH = re.compile(r"(?:员工|职工|雇员)(?:人数)?\s*(\d{2,6})\s*(?:余)?\s*(?:名|人)")
CUR = r"(USD|US\$|U\.S\.\s?\$|\$|EUR|€|GBP|£|RMB|CNY|¥|INR|₹|Rs\.?|TRY|₺|BRL|R\$|AED|SAR|JPY|KRW|ZAR)"
REVENUE = re.compile(r"(?:annual |yearly |total )?(?:turnover|revenue|revenues|sales volume|annual sales|sales of|facturaci[oó]n|faturamento|umsatz|chiffre d'affaires|销售额|营业额|年产值)"
                     r"[^.\n]{0,40}?" + CUR + r"\s?(\d+(?:[.,]\d+)?)\s*(billion|bn|million|mn|mio|m|crore|cr|lakh|亿|万)?\b", re.I)
CAPACITY = re.compile(r"(\d{1,3}(?:[,.\s]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:million\s+|thousand\s+)?(?:metric\s+)?(tons?|tonnes?|mt|units|pieces|pcs|sets|litres|liters|bags|square meters|sqm|m2|m²|acres|hectares|ha)\s*"
                      r"(?:per|/|a|each)\s*(year|annum|month|day|yr)", re.I)
AREA = re.compile(r"(?:cover(?:s|ing)?|area of|occup(?:y|ies|ying)|spread over|plant of|factory of|facility of)\s*(?:an area of\s*)?(?:over|more than|about)?\s*"
                  r"(\d{1,3}(?:[,.\s]\d{3})*|\d+)\s*(square meters|square metres|sqm|m2|m²|sq\.? ?ft|square feet|acres|hectares|ha|平方米)", re.I)
MULT = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "mio": 1e6, "m": 1e6, "crore": 1e7, "cr": 1e7, "lakh": 1e5, "亿": 1e8, "万": 1e4}
# rough USD per unit, only to place a stated revenue in a size band (the stated amount and currency are kept as printed)
USD_PER = {"USD": 1, "US$": 1, "$": 1, "EUR": 1.08, "€": 1.08, "GBP": 1.27, "£": 1.27, "RMB": 0.14, "CNY": 0.14, "¥": 0.14, "INR": 0.012, "₹": 0.012,
           "RS": 0.012, "TRY": 0.03, "₺": 0.03, "BRL": 0.18, "R$": 0.18, "AED": 0.27, "SAR": 0.27, "JPY": 0.0067, "KRW": 0.00072, "ZAR": 0.055}


def _int(s):
    d = re.sub(r"[,.\s]", "", s)
    return int(d) if d.isdigit() else None


def profile_on(pages, structured=None):
    """Founding year, employees, revenue, capacity and plant area the site states, each with its phrase and page."""
    structured = structured or {}
    out = {}
    if structured.get("founded"):
        y = re.search(r"(18|19|20)\d\d", structured["founded"])
        if y and 1800 <= int(y.group(0)) <= THIS_YEAR:
            out["founded"] = {"value": int(y.group(0)), "phrase": f"foundingDate {structured['founded']}", "source": pages[0][0], "basis": "schema.org data on the site"}
    if structured.get("employees") and _int(str(structured["employees"]).split("-")[0]):
        out["employees"] = {"value": _int(str(structured["employees"]).split("-")[0]), "phrase": f"numberOfEmployees {structured['employees']}", "source": pages[0][0], "basis": "schema.org data on the site"}
    for url, page in pages:
        t = _text(page)
        if "founded" not in out:
            ys = [(int(m.group(1)), m.group(0)) for m in FOUNDED.finditer(t) if 1800 <= int(m.group(1)) <= THIS_YEAR]
            if not ys and urlsplit(url).path in ("", "/"):  # "since 1987" only on the home page, where it is the company's own line
                ys = [(int(m.group(1)), m.group(0)) for m in SINCE.finditer(t) if 1800 <= int(m.group(1)) <= THIS_YEAR - 2]
            if ys:
                y, ph = min(ys)  # the earliest stated year is the founding (later ones are milestones)
                out["founded"] = {"value": y, "phrase": ph[:80], "source": url, "basis": "stated on the site"}
        if "employees" not in out:
            m = EMPLOYEES.search(t) or EMPLOYEES_ZH.search(t)
            if m:
                n = _int(m.group(1))
                if n and 3 <= n <= 2_000_000:
                    out["employees"] = {"value": n, "phrase": m.group(0)[:80], "source": url, "basis": "stated on the site"}
        if "revenue" not in out:
            m = REVENUE.search(t)
            if m:
                cur = m.group(1).upper().replace("U.S. $", "USD").replace("U.S.$", "USD").rstrip(".")
                try:
                    amt = float(m.group(2).replace(",", ".")) * MULT.get((m.group(3) or "").lower(), 1)
                except ValueError:
                    amt = 0
                if amt >= 1e4:
                    usd = amt * USD_PER.get(cur, 0) if USD_PER.get(cur) else None
                    out["revenue"] = {"value": amt, "currency": cur, "usd_approx": round(usd) if usd else None, "phrase": m.group(0)[:100], "source": url, "basis": "stated on the site"}
        if "capacity" not in out:
            m = CAPACITY.search(t)
            if m:
                out["capacity"] = {"phrase": m.group(0)[:80], "source": url, "basis": "stated on the site"}
        if "plant_area" not in out:
            m = AREA.search(t)
            if m:
                out["plant_area"] = {"phrase": m.group(0)[:80], "source": url, "basis": "stated on the site"}
    if "founded" in out:
        out["years_in_business"] = THIS_YEAR - out["founded"]["value"]
    out["size"] = size_band(out)
    return out


def size_band(p, record_employees=None):
    """small / mid / large from the stated employees (under 50, 50-999, 1000+), else the stated revenue
    (under USD 10M, 10-500M, over 500M), else the record's employee count; "not stated" when none."""
    e = (p.get("employees") or {}).get("value")
    if e:
        return {"band": "small" if e < 50 else "mid" if e < 1000 else "large", "basis": f"{e:,} employees ({p['employees']['basis']})"}
    usd = (p.get("revenue") or {}).get("usd_approx")
    if usd:
        return {"band": "small" if usd < 1e7 else "mid" if usd < 5e8 else "large", "basis": f"revenue about USD {usd / 1e6:,.0f}M ({p['revenue']['basis']})"}
    if record_employees:
        try:
            e = int(float(str(record_employees).replace(",", "")))
            return {"band": "small" if e < 50 else "mid" if e < 1000 else "large", "basis": f"{e:,} employees (supplier record)"}
        except ValueError:
            pass
    return {"band": "not stated", "basis": ""}


# ---------------------------------------------------------------- summary (assembled, not written)
def summary(name, country_name, check, prof, people=None):
    """A short factual summary built only from gathered fields; parts with no source are left out."""
    roles = [r["role"] for r in check.get("roles") or []]
    kind = {"manufacturer": "manufacturer", "trader": "trader / distributor", "epc": "contractor (EPC)", "service": "service company"}
    what = " and ".join(kind[r] for r in roles if r in kind) or "company"
    s = [f"{name} is a {what}" + (f" in {country_name}" if country_name else "") +
         (f", founded in {prof['founded']['value']} ({prof['years_in_business']} years)" if prof.get("founded") else "") + "."]
    d = (check.get("description") or "").strip()
    if d:
        d = re.split(r"(?<=[.!?])\s", d)[0][:220]
        s.append(f"In its own words: \"{d}\"")
    if check.get("products"):
        s.append("Products named on its site: " + ", ".join(check["products"][:6]) + ".")
    size = prof.get("size") or {}
    if size.get("band") and size["band"] != "not stated":
        s.append(f"Size: {size['band']} ({size['basis']}).")
    if prof.get("capacity"):
        s.append(f"States capacity: {prof['capacity']['phrase']}.")
    if prof.get("revenue"):
        s.append(f"States revenue: {prof['revenue']['phrase']}.")
    if check.get("certificates"):
        s.append("Certificates named: " + ", ".join(check["certificates"][:5]) + ".")
    if check.get("export_countries"):
        s.append(f"Names {len(check['export_countries'])} export countries.")
    return " ".join(s)[:900]


def extract(pages, name, country, check):
    """Everything above for one site (pure). `check` is company_check.analyse's result for the same pages."""
    prof = profile_on(pages, check.get("structured"))
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=country)
        cname = (getattr(c, "common_name", None) or c.name) if c else ""
    except Exception:  # noqa: BLE001
        cname = ""
    people = people_on(pages)
    return {
        "profile_version": PROFILE_VERSION,
        "wechat": wechat_on(pages),
        "whatsapp_links": whatsapp_on(pages, check.get("whatsapp"), country),
        "people": people,
        "profile": prof,
        "summary": summary(name, cname, check, prof, people),
    }


# ---------------------------------------------------------------- press (network; server job)
LEGAL_TAIL = re.compile(r"[\s,]+(?:co\.?,?\s*)?(?:ltd\.?|limited|llc|inc\.?|gmbh|ag|s\.?a\.?|s\.?p\.?a\.?|s\.?r\.?l\.?|b\.?v\.?|plc|pvt\.?|private|corp\.?|corporation|company|sa de cv|ltda\.?)\.?$", re.I)


def press_name(name):
    """The name to search in the press: legal suffixes off; None when too short or too generic to be unambiguous."""
    n = re.sub(r"\s+", " ", name or "").strip()
    for _ in range(2):
        n = LEGAL_TAIL.sub("", n).strip(" ,.")
    words = [w for w in re.findall(r"[\w&'-]+", n) if len(w) > 1]
    if len(n) < 6 or len(words) < 2 and len(n) < 9:
        return None
    if re.fullmatch(r"(?i)(the )?(national|general|international|global|united|first|new|best|golden|royal|star|asia|africa|euro)[\w ]{0,12}", n):
        return None
    return n


PRESS_JUNK = re.compile(r"stock price|price, news|quote (and|&) history|seasonal returns|returns chart|number of employees|headcount data|"
                        r"stock overview|undervalued|working capital per share|share price|\(\w+\.\w{1,3}\) stock|company profile|org chart", re.I)


def press_filter(items, name, country_names, domain=""):
    """Google News RSS items -> articles about this company: the exact name in the title, and the country named in the
    title or the outlet in that country (or the company's own domain as the source), to keep namesakes out."""
    n = press_name(name)
    if not n:
        return []
    # case-sensitive unless the record is all capitals: "Australian Agricultural" is a name, "Australian agricultural" is not
    rx = re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])", re.I if n.isupper() else 0)
    out = []
    for it in items:
        t = it.get("title", "")
        if not rx.search(t) or PRESS_JUNK.search(t):
            continue
        ctry = any(re.search(r"(?<![\w])" + re.escape(c) + r"(?![\w])", t + " " + it.get("outlet", ""), re.I) for c in country_names if c)
        own = domain and domain in it.get("outlet_url", "")
        distinctive = len(n) >= 14 and len(n.split()) >= 2
        if not (ctry or own or distinctive):
            continue
        out.append({**it, "match": "exact name" + (", country named" if ctry else ", own domain" if own else ", distinctive name")})
    return out[:5]


def parse_rss(xml):
    """Google News RSS -> [{"title", "url", "outlet", "outlet_url", "date"}] (stdlib XML parser)."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for it in root.iter("item"):
        src = it.find("source")
        title = (it.findtext("title") or "").strip()
        outlet = (src.text or "").strip() if src is not None else ""
        if outlet and title.endswith(" - " + outlet):
            title = title[: -len(outlet) - 3]
        try:
            d = parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            d = ""
        out.append({"title": title[:200], "url": (it.findtext("link") or "")[:400], "outlet": outlet[:80],
                    "outlet_url": (src.get("url") if src is not None else "") or "", "date": d})
    return out


# ---------------------------------------------------------------- search snippets for linkedin.com/in (network; server job)
def parse_ddg(page):
    """DuckDuckGo HTML results -> [{"url", "title", "snippet"}]."""
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', page, re.S):
        url = html.unescape(m.group(1))
        um = re.search(r"uddg=([^&]+)", url)
        if um:
            from urllib.parse import unquote
            url = unquote(um.group(1))
        out.append({"url": url, "title": html.unescape(TAG.sub("", m.group(2))).strip(), "snippet": html.unescape(TAG.sub("", m.group(3))).strip()})
    return out


def snippet_people(results, company, role_words=None):
    """Search results -> [{"name", "title", "role", "linkedin", "confidence": "search snippet"}] where the result is a
    linkedin.com/in profile whose title or snippet names the company and a target role."""
    n = press_name(company) or company
    core = re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])", re.I)
    out = []
    for r in results:
        if not LI_IN.match(r["url"]):
            continue
        blob = f"{r['title']} {r['snippet']}"
        if not core.search(blob):
            continue
        # LinkedIn result titles read "Name - Title - Company | LinkedIn"
        parts = [p.strip() for p in re.split(r"\s[-–|]\s", r["title"].replace(" | LinkedIn", "")) if p.strip()]
        if len(parts) < 2:
            continue
        name = _clean_name(parts[0])
        title = next((p for p in parts[1:] if ANY_ROLE.search(p)), "")
        if not title:
            m = ANY_ROLE.search(r["snippet"])
            title = m.group(0) if m else ""
        role = _role_of(title)
        if name and role and not any(x["name"] == name for x in out):
            out.append({"name": name, "title": title[:80], "role": role, "linkedin": r["url"].split("?")[0][:200],
                        "source": r["url"].split("?")[0][:200], "basis": "public search result snippet naming the company and the title",
                        "confidence": "search snippet"})
    return out[:4]


# ---------------------------------------------------------------- Wikidata facts (network; server job)
def wikidata_facts(entity, domain):
    """wbgetentities entity -> facts, only when its official website (P856) is on this domain."""
    cl = entity.get("claims") or {}

    def vals(p):
        out = []
        for c in cl.get(p, []):
            dv = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if dv is not None:
                out.append((dv, c))
        return out
    sites = [v for v, _ in vals("P856") if isinstance(v, str)]
    if not any(_dom(u) == domain or _dom(u).endswith("." + domain) or domain.endswith("." + _dom(u)) for u in sites):
        return None
    f = {"qid": entity.get("id"), "source": f"https://www.wikidata.org/wiki/{entity.get('id')}"}
    for v, _ in vals("P571")[:1]:
        y = re.match(r"[+-](\d{4})", v.get("time", "")) if isinstance(v, dict) else None
        if y:
            f["founded"] = int(y.group(1))
    emp = [(v, c) for v, c in vals("P1128") if isinstance(v, dict)]
    if emp:
        v, _ = emp[-1]
        try:
            f["employees"] = int(float(v.get("amount", "0")))
        except ValueError:
            pass
    rev = [(v, c) for v, c in vals("P2139") if isinstance(v, dict)]
    if rev:
        v, c = rev[-1]
        unit = v.get("unit", "").rsplit("/", 1)[-1]
        y = ((c.get("qualifiers") or {}).get("P585") or [{}])[0].get("datavalue", {}).get("value", {}).get("time", "")[1:5]
        try:
            f["revenue"] = {"amount": float(v.get("amount", "0")), "unit_qid": unit, "year": y}
        except ValueError:
            pass
    for p, k in (("P169", "ceo_qids"), ("P112", "founder_qids")):
        q = [v.get("id") for v, _ in vals(p) if isinstance(v, dict) and v.get("id")]
        if q:
            f[k] = q[:3]
    return f


def _dom(u):
    h = urlsplit(u if "//" in u else "http://" + u).netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h
