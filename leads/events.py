"""World and project intelligence (spec phase 4): structured events, dedup, change detection, project timelines.

Deterministic, no model calls. Every run reads what the pipeline already holds and turns it into typed events:
  - news: briefing_items.csv (topic feeds) and news.csv (country press), typed by keyword rules (English plus
    Spanish, French and Portuguese words seen in notice titles);
  - official records: the tender chunks (data/leads/sheet/tenders_*.csv; stage=planned rows are pipeline projects,
    general procurement notices and prior information), MDB open tenders and big international open tenders,
    World Bank procurement plans (wb_plans.csv), World Bank contract awards (wb_awards.csv) and big awards (awards.csv).
Each event separates project country, buyer country, supplier country, publisher country and affected markets.

Dedup: news items cluster by normalized title + shared entity (country or company) + a 10-day window. A near-identical
title from another publisher is a mirror (syndicated copy), never an independent confirmation; a differently worded
report from another publisher is an independent source. Google News links all share one host, so the publisher name
stands in for the URL host there; other links use their real host.
Change detection against the previous data/leads/events.csv: new / updated (material field changed or a new
independent source) / republished (same announcement again under a later date or another link) / seen (same record
again) / carried (kept from history, not in today's inputs). Republishing never creates a new event.
Linking: World Bank project ids (pipeline, plans, awards; open WB notices by project name), IDB operation numbers,
AIIB / AfDB / IsDB project names, then buyer + title similarity (planned row -> open tender, award -> notice) and,
conservatively, news -> project by distinctive name tokens in the same country.
Outputs: data/leads/events.csv, data/leads/project_timelines.csv.   Run after the merge: python -m leads.events
"""
import csv
import datetime as dt
import glob
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from urllib.parse import urlparse

from .common import LEADS, log, today

csv.field_size_limit(10_000_000)

# ---------------------------------------------------------------- text helpers
STOP = set("""a an the of for and or in on at to by with from as is are was were be been its it this that new over into
amid after before under about via per vs de del la las los el y en para por con un una al le les des du et au aux pour sur
dans par une da do dos das e em no na nos nas ao um uma""".split())


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def toks(s):
    return {w for w in norm(s).split() if w not in STOP and (len(w) > 2 or w.isdigit())}


def jacc(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def title_key(t):
    return " ".join([w for w in norm(t).split() if w not in STOP][:14])


def num(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if f == f and abs(f) != float("inf") else 0.0
    except (TypeError, ValueError):
        return 0.0


def d10(v):
    v = str(v or "").strip()
    if re.fullmatch(r"\d{8}", v):
        v = f"{v[:4]}-{v[4:6]}-{v[6:]}"
    return v[:10] if re.match(r"\d{4}-\d{2}-\d{2}", v) else ""


def sha(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- event typing
# order matters: the first match is the primary type, the rest become tags
TYPES = [
    ("financing_approval", r"\b(board approves?|approves? (a |an )?(\$|us\$|usd)?[\d.,]* ?(m|mn|bn|million|billion)? ?(loan|financing|credit|grant|funding)|"
                           r"(loan|financing|credit|grant|funding) (is |was )?approved|approved (a |an )?(\$|us\$)?[\d.,]* ?(million|billion|mn|bn)? ?(loan|financing|credit|grant)|"
                           r"(loan|financing|credit|funding) approval|financing agreement|loan agreement|grant agreement|financial close|secures? (\$|us\$)?[\d.,]+ ?(m|mn|bn|million|billion)? ?(in )?(loan|financing|funding|debt)|"
                           r"aprueba (un )?(prestamo|financiamiento|credito)|prestamo aprobado|approuve (un )?(pret|financement)|aprova (financiamento|emprestimo))\b"),
    ("epc_selection", r"\b(epc (contract|contractor|deal|award)|selected as (the )?(epc|contractor)|turnkey contract|preferred bidder|"
                      r"engineering, procurement and construction|appointed (as )?(the )?(main |epc )?contractor|epc partner)\b"),
    ("construction_start", r"\b(breaks? ground|ground-?breaking|construction (begins|began|starts|started|commenced|kicks off|is under way|underway)|"
                           r"foundation stone|first concrete|starts? construction|begins? construction|commences? construction|"
                           r"inicio de (las )?obras|inicia(n)? (las )?obras|debut des travaux|lancement des travaux|inicio das obras)\b"),
    ("feasibility_permitting", r"\b(feasibility stud(y|ies)|pre-?feasibility|front-?end engineering|\bfeed\b (study|contract)|environmental (impact )?(assessment|approval|permit|clearance)|"
                               r"\besia\b|\beia\b|permit (granted|issued|approved)|licen[cs]e (granted|issued|awarded)|preliminary design|detailed design|"
                               r"estudio(s)? de (pre)?factibilidad|etude(s)? de (pre)?faisabilite|estudo(s)? de viabilidade|licencia ambiental)\b"),
    ("tender_amendment", r"\b(corrigendum|addendum|amendment|amienda|enmienda|modificacion|rectificatif|avis rectificatif|deadline extended|"
                         r"extension of (the )?(bid |submission )?deadline|updated specific procurement notice|re-?tender(ed)?|cancell?ation of (the )?tender)\b"),
    ("tender_publication", r"\b(invites? (bids|tenders|proposals|expressions? of interest)|invitation for (bids|prequalification|tenders)|tender (launched|issued|floated|opens?)|"
                           r"floats? (a )?tender|issues? (a )?tender|request for (proposals|bids|quotations|expressions? of interest)|call for (tenders|bids|proposals)|"
                           r"tenders? for [\d\w]|licitacion publica|convocatoria|appel d.offres|licitacao|pregao|specific procurement notice)\b"),
    ("planned_procurement", r"\b(procurement plan|general procurement notice|prior information notice|advance procurement notice|plan anual de (adquisiciones|contrataciones)|"
                            r"aviso general de adquisiciones|avis general de passation|presolicitation|pre-?solicitation|anuncio previo|informacion previa)\b"),
    ("expected_procurement_package", r"\b(sources sought|early market engagement|market sounding|request for information|plans? to (buy|purchase|procure|acquire)|"
                                     r"will (procure|purchase|buy)|to procure|seeks? (suppliers|vendors|bidders|partners)|looking for suppliers)\b"),
    ("award", r"\b(awarded|awards? (a |an |the )?(\$|us\$)?[\w.,]* ?contract|wins? (a |an |the )?[\w$.,\- ]{0,40}(contract|order|deal|tender|bid)|won (a |an |the )?[\w$.,\- ]{0,40}(contract|order|tender)|"
              r"contract award|secures? (a |an |the )?[\w$.,\- ]{0,40}(contract|order)|bags? (a |an |the )?[\w$.,\- ]{0,40}(contract|order|deal)|lands? (a |an |the )?[\w$.,\- ]{0,30}contract|"
              r"signs? (a |an |the )?[\w$.,\- ]{0,40}contract|adjudica(cion|do|da)|adjudicacao|attribution du marche|attribue)\b"),
    ("trade_policy_change", r"\b(tariffs?|import dut(y|ies)|export dut(y|ies)|customs dut(y|ies)|sanctions?|sanctioned|export ban|import ban|export controls?|quotas?|anti-?dumping|countervailing|"
                            r"safeguard dut(y|ies)|trade deal|trade agreement|free trade|\bfta\b|embargo|aranceles?|droits de douane|tarifas)\b"),
    ("supply_disruption", r"\b(strikes?|walkout|outage|shut ?down|halts?|halted|suspends?|suspended|closure|closed|blockade|attacks?|attacked|congestion|force majeure|disrupt\w*|"
                          r"floods?|flooding|drought|fire at|explosion|blast|derail\w*|shortages?|stoppage|delays? at|backlog|hit by|damaged|damages|sabotage|accident|"
                          r"detain(s|ed)?|seiz(e|es|ed|ure))\b"),
    ("material_price_logistics", r"\b(prices?|freight rates?|container rates?|shipping rates?|charter rates?|baltic dry|bunker|surcharge|futures|per tonne|per ton|/t\b|"
                                 r"record high|record low|surges?|slumps?|rall(y|ies)|plunges?|soars?|jumps?|tumbles?|resum\w+ (\w+ ){0,3}(sailings|services?|transits?|loadings|shipping)|"
                                 r"rerout\w+|sailings)\b"),
    ("project_announcement", r"\b(to build|will build|plans? (to build|a new)|announces? (a |an )?(new )?(project|plant|factory|refinery|terminal|facility|investment)|unveils?|"
                             r"to set up|to construct|to develop|to invest|invests?|investment of|new (plant|factory|refinery|port|terminal|power plant|mine|smelter|line)|"
                             r"\bmou\b|memorandum of understanding|proposed (project|plant)|\d+ ?(mw|gw|mtpa)\b|expansion (project|plan)|pledges? (us\$|\$|usd)|"
                             r"approves? (the )?(revival|construction|project|plan|development)|eyes (raising|building|expanding)|mulls)\b"),
]
TYPE_RX = [(t, re.compile(rx, re.I)) for t, rx in TYPES]
SUPPLY_CTX = re.compile(r"\b(port|ports|shipping|vessels?|tankers?|cargo|freight|containers?|pipelines?|refiner(y|ies)|plants?|mines?|mining|rail|railways?|"
                        r"factor(y|ies)|supply|supplies|exports?|imports?|grid|power|electricity|oil|gas|lng|red sea|suez|hormuz|strait|canal|terminal|"
                        r"airport|truck(ers|ing)?|dock(workers|s)?|chips?|semiconductors?|fertili[sz]er|wheat|steel|copper|smelter)\b", re.I)
PRICE_CTX = re.compile(r"\b(wheat|maize|corn|rice|sugar|palm oil|soy\w*|urea|fertili[sz]er|dap|ammonia|steel|rebar|iron ore|copper|aluminium|aluminum|zinc|nickel|"
                       r"lithium|cobalt|coal|crude|oil|brent|wti|diesel|gasoil|lng|gas|cement|freight|container|shipping|baltic|bunker|cocoa|coffee|cotton|"
                       r"rubber|polymer|polyethylene|pvc|gold|silver|commodit\w+)\b", re.I)
NOT_PRICE = re.compile(r"\b(share price|stock|shares|sensex|nifty|equities|ipo|price target|bitcoin|crypto|ticket prices|house prices|home prices)\b", re.I)
NOT_BIZ = re.compile(r"\b(soccer|football|player|club|coach|striker|nba|nfl|cricket|film|movie|album|actor|actress|singer)\b", re.I)
COUNTRY_SUBJECT = re.compile(r"^(China|India|Turkey|T\u00fcrkiye|Korea|South Korea|Japan|Israel|UAE|Saudi Arabia|Egypt|Russia|Germany|France|Italy|Spain|Brazil|"
                             r"Vietnam|Indonesia|Malaysia|Pakistan|Qatar|Iran)(?:['\u2019]s)?\s+(?:[A-Z][\w&-]+\s+){0,3}(wins|signs|secures|bags|lands|to build|will build|unveils|invests|to invest)\b")
MIL_STRIKE = re.compile(r"\b(air ?strikes?|missile strikes?|drone strikes?|military strikes?|strikes? on)\b", re.I)


def classify(text):
    """(primary type, [secondary tags]) from title + summary; '' when nothing applies."""
    hits = []
    for t, rx in TYPE_RX:
        if not rx.search(text):
            continue
        if t == "material_price_logistics" and (NOT_PRICE.search(text) or not PRICE_CTX.search(text)):
            continue
        if t == "supply_disruption" and not SUPPLY_CTX.search(text):
            continue
        if t in ("award", "epc_selection") and NOT_BIZ.search(text):
            continue
        hits.append(t)
    if not hits:
        return "", []
    return hits[0], hits[1:]


# ---------------------------------------------------------------- countries and actors
DEMONYM = {"chinese": "CHN", "china's": "CHN", "indian": "IND", "india's": "IND", "turkish": "TUR", "korean": "KOR", "south korean": "KOR",
           "japanese": "JPN", "israeli": "ISR", "emirati": "ARE", "saudi": "SAU", "egyptian": "EGY", "russian": "RUS", "american": "USA",
           "us-based": "USA", "u.s.": "USA", "german": "DEU", "french": "FRA", "italian": "ITA", "spanish": "ESP", "british": "GBR",
           "brazilian": "BRA", "vietnamese": "VNM", "indonesian": "IDN", "malaysian": "MYS", "pakistani": "PAK", "qatari": "QAT",
           "iranian": "IRN", "kenyan": "KEN", "nigerian": "NGA", "ethiopian": "ETH", "moroccan": "MAR", "omani": "OMN", "kuwaiti": "KWT",
           "singaporean": "SGP", "thai": "THA", "filipino": "PHL", "south african": "ZAF", "mexican": "MEX", "chilean": "CHL",
           "colombian": "COL", "peruvian": "PER", "argentine": "ARG", "australian": "AUS", "canadian": "CAN", "dutch": "NLD", "swiss": "CHE"}
SUPPLIER_NOUN = r"(firms?|compan(y|ies)|contractors?|consortium|group|giant|developers?|state-owned|manufacturers?|makers?|suppliers?|epc|builders?|investors?|exporters?)"
DEMONYM_RX = re.compile(r"\b(" + "|".join(sorted(map(re.escape, DEMONYM), key=len, reverse=True)) + r")\s+(?:[\w-]+\s+){0,2}" + SUPPLIER_NOUN + r"\b", re.I)
KNOWN_FIRMS = [(re.compile(r"\b(power ?china|sinohydro|china (railway|road|harbour|energy|communications|state construction|national|machinery|gezhouba)|cscec|crcc|crbc|"
                           r"cccc|chec|sinopec|cnpc|petrochina|huawei|zte|byd|longi|jinko|trina|catl|cnnc|state grid|sany|xcmg|zoomlion)\b", re.I), "CHN"),
               (re.compile(r"\b(larsen|l&t|tata (projects|power|steel)|adani|reliance|bhel|kec international|kalpataru|afcons|nhpc|ntpc)\b", re.I), "IND"),
               (re.compile(r"\b(limak|kalyon|yapi merkezi|ronesans|enka|cengiz|kolin|aksa)\b", re.I), "TUR"),
               (re.compile(r"\b(hyundai|samsung c&t|doosan|daewoo e&c|posco|kepco|gs e&c|sk ecoplant)\b", re.I), "KOR"),
               (re.compile(r"\b(elbit|rafael|iai|israel aerospace|netafim|ide technologies|mekorot)\b", re.I), "ISR")]
PUBLISHER = {"reuters": "GBR", "bloomberg": "USA", "bloomberg.com": "USA", "tradingview": "USA", "energynow.com": "CAN", "middle east eye": "GBR",
             "the times of india": "IND", "the economic times": "IND", "business standard": "IND", "hindustan times": "IND", "the hindu": "IND",
             "vietnam.vn": "VNM", "vnexpress": "VNM", "the edge malaysia": "MYS", "the star": "MYS", "mexico business news": "MEX", "bnamericas": "CHL",
             "india shipping news": "IND", "the jerusalem post": "ISR", "times of israel": "ISR", "globes": "ISR", "haaretz": "ISR", "ynetnews": "ISR",
             "saudigulf projects": "SAU", "arab news": "SAU", "gulf news": "ARE", "the national": "ARE", "zawya": "ARE", "khaleej times": "ARE",
             "ahram online": "EGY", "daily news egypt": "EGY", "business daily": "KEN", "the east african": "KEN", "punch newspapers": "NGA",
             "premium times": "NGA", "the citizen": "TZA", "dawn": "PAK", "the express tribune": "PAK", "the daily star": "BGD", "xinhua": "CHN",
             "global times": "CHN", "south china morning post": "HKG", "nikkei asia": "JPN", "financial times": "GBR", "the guardian": "GBR",
             "bbc": "GBR", "cnbc": "USA", "the wall street journal": "USA", "ap news": "USA", "afp": "FRA", "le monde": "FRA", "dw": "DEU",
             "hellenic shipping news": "GRC", "splash247": "SGP", "lloyd's list": "GBR", "tradewinds": "NOR", "argus media": "GBR",
             "s&p global": "USA", "fastmarkets": "GBR", "mining weekly": "ZAF", "engineering news": "ZAF", "biggo finance": "TWN", "traders union": "GBR"}
TLD = {"in": "IND", "vn": "VNM", "my": "MYS", "za": "ZAF", "ng": "NGA", "ke": "KEN", "pk": "PAK", "bd": "BGD", "lk": "LKA", "ae": "ARE", "sa": "SAU",
       "eg": "EGY", "il": "ISR", "tr": "TUR", "br": "BRA", "mx": "MEX", "co": "COL", "cl": "CHL", "pe": "PER", "ar": "ARG", "id": "IDN", "ph": "PHL",
       "th": "THA", "cn": "CHN", "uk": "GBR", "de": "DEU", "fr": "FRA", "it": "ITA", "es": "ESP", "pl": "POL", "ru": "RUS", "jp": "JPN", "kr": "KOR",
       "au": "AUS", "ca": "CAN", "gh": "GHA", "tz": "TZA", "ug": "UGA", "et": "ETH", "ma": "MAR", "qa": "QAT", "om": "OMN", "kw": "KWT", "sg": "SGP"}
CHOKEPOINTS = re.compile(r"\b(red sea|suez|hormuz|bab el-?mandeb|panama canal|malacca|bosphorus|black sea|cape of good hope)\b", re.I)
LEAD_RX = re.compile(r"\b([A-Z][\w&.'-]+(?: [A-Z][\w&.'-]+){0,4}) (?:to build|will build|plans? to build|breaks ground on|awarded|wins|won|signs|secures|bags|lands|"
                     r"to invest|invests|to expand|to set up|to construct|commissions|selected|appointed)\b")
GENERIC_LEAD = re.compile(r"^(the |a )?(contractor|government|ministry|company|firm|consortium|group|state|president|minister|officials?|report|why|how|what|when|"
                          r"china|india|us|uk|eu|world bank|imf|new|cabinet|council|city|board)$", re.I)
_C = {}


def countries_in(text):
    if not _C:
        from .briefing import _countries
        _C.update(_countries())
    out = []
    for n, c in _C.items():
        if n in text and re.search(r"\b" + re.escape(n) + r"\b", text) and c not in out:
            out.append(c)
    return out[:6]


def publisher_country(name, url=""):
    k = (name or "").strip().lower()
    if k in PUBLISHER:
        return PUBLISHER[k]
    host = urlparse(url or "").netloc.lower()
    if host and "news.google" not in host:
        tld = host.rsplit(".", 1)[-1]
        if tld in TLD:
            return TLD[tld]
    cs = countries_in(name or "")
    if cs:
        return cs[0]
    m = re.search(r"\b(" + "|".join(map(re.escape, DEMONYM)) + r")\b", k)
    return DEMONYM[m.group(1)] if m else ""


def host_of(source, url):
    h = urlparse(url or "").netloc.lower().replace("www.", "")
    return (source or "").strip().lower() if (not h or "news.google" in h) else h


def supplier_country(text, project_country):
    m = COUNTRY_SUBJECT.match(text or "")
    if m:
        c = countries_in(m.group(1)) or [{"Korea": "KOR", "South Korea": "KOR", "UAE": "ARE", "Vietnam": "VNM", "Iran": "IRN", "Russia": "RUS"}.get(m.group(1), "")]
        if c and c[0] and c[0] != project_country:
            return c[0]
    for m in DEMONYM_RX.finditer(text):
        c = DEMONYM.get(m.group(1).lower())
        if c and c != project_country:
            return c
    for rx, c in KNOWN_FIRMS:
        if rx.search(text) and c != project_country:
            return c
    return ""


def actors_in(title, lead=""):
    out = []
    if lead:
        out.append(lead)
    for m in LEAD_RX.finditer(title):
        a = m.group(1).strip()
        if len(a) > 3 and not GENERIC_LEAD.match(a) and a not in out and a not in (_C or {}) and not COUNTRY_SUBJECT.match(a + " wins"):
            out.append(a)
    for rx, _ in KNOWN_FIRMS:
        m = rx.search(title)
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out[:4]


# ---------------------------------------------------------------- money
FX = {}
MONEY = re.compile(r"(us\$|usd|\$|eur|€|inr|rs\.?|₹|cny|rmb|yuan)\s?([\d][\d.,]*)\s?(trillion|tn|billion|bn|b\b|million|mn|mln|m\b|crore|cr\b|lakh|k\b)?|"
                   r"([\d][\d.,]*)\s?(trillion|billion|million|bn|mn|crore)\s?(dollars|usd|euros?|eur|rupees|inr|yuan)", re.I)
MULT = {"trillion": 1e12, "tn": 1e12, "billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6, "mln": 1e6, "m": 1e6, "crore": 1e7, "cr": 1e7, "lakh": 1e5, "k": 1e3}
CUR = {"us$": "USD", "usd": "USD", "$": "USD", "dollars": "USD", "eur": "EUR", "€": "EUR", "euro": "EUR", "euros": "EUR", "inr": "INR", "rs": "INR", "rs.": "INR",
       "₹": "INR", "rupees": "INR", "cny": "CNY", "rmb": "CNY", "yuan": "CNY"}


def _fx():
    if not FX:
        FX["USD"] = 1.0
        p = LEADS / "fx.csv"
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                if num(r.get("usd_per_unit")):
                    FX[r["currency"]] = num(r["usd_per_unit"])
    return FX


def money_usd(text):
    """Largest stated amount in USD (only currencies with a published rate in fx.csv), else 0."""
    best = 0.0
    for m in MONEY.finditer(text or ""):
        if m.group(2):
            cur, amt, mul = CUR.get(m.group(1).lower(), ""), m.group(2), (m.group(3) or "").lower()
        else:
            amt, mul, cur = m.group(4), m.group(5).lower(), CUR.get(m.group(6).lower().rstrip("s") if m.group(6).lower() != "dollars" else "dollars", "")
            cur = cur or CUR.get(m.group(6).lower(), "")
        v = num(amt.rstrip(".,"))
        rate = _fx().get(cur)
        if not v or not rate or not mul:
            continue  # a bare number without a scale is too often a year or a count
        best = max(best, v * MULT.get(mul, 1) * rate)
    return round(best) if best < 5e12 else 0


# ---------------------------------------------------------------- inputs
def _rows(name):
    p = LEADS / name
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def tender_rows():
    rows = []
    for fn in sorted(glob.glob(str(LEADS / "sheet" / "tenders_*.csv"))):
        rows.extend(csv.DictReader(open(fn, encoding="utf-8")))
    extra = {}
    p = LEADS / "tenders_all.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            extra[r["id"]] = (d10(r.get("published")), d10(r.get("first_seen")))
    for r in rows:
        r["_pub"], r["_first"] = extra.get(r.get("id"), ("", ""))
    return rows


MDB = {"World Bank", "World Bank pipeline", "AfDB", "AIIB", "IsDB", "IDB", "EBRD", "UNDP"}
INTL = re.compile(r"international|world bank|\bicb\b|gpa|open to foreign|foreign firms", re.I)
AMEND = re.compile(TYPES[4][1], re.I)
WB_SEP = re.compile(r"\s*(?:\||&#124;|\b124\s*[;,])\s*")
DOC_PREFIX = re.compile(r"^(pmp|ppm|agpm|gpn|spn|ppn|aga|aoi|ami|eoi|procurement notice|general procurement notice|avis general de passation des marches)\s*[-:]\s*", re.I)
DPF = re.compile(r"\b(dpf|dpo|development policy|budget support|policy-based|cat ddo)\b", re.I)


def wb_project_name(title):
    parts = [p for p in WB_SEP.split(title or "") if p.strip()]
    return (parts[-1] if parts else title or "").strip(" -;,)")


def mdb_project(r):
    """(project key, ref, name) for an MDB planned/open row, or ('', '', '')."""
    src, c, title, buyer = r.get("source", ""), r.get("country", ""), r.get("title_en", ""), r.get("buyer", "")
    if r.get("id", "").startswith("WBP-"):
        pid = r["id"][4:]
        return f"WB:{pid}", pid, re.sub(r"\s*\([^()]*\)\s*$", "", title).strip()
    if src == "World Bank":
        n = wb_project_name(title)
        return f"WBN:{c}:{norm(n)[:80]}", "", n
    if src == "IDB":
        m = re.search(r"\b([A-Z]{2}-[A-Z]\d{4})\b", buyer + " " + title)
        return (f"IDB:{m.group(1)}", m.group(1), buyer) if m else ("", "", "")
    if src == "AIIB":
        n = re.sub(r"\s*\(AIIB-financed\)\s*$", "", buyer).strip()
        m = re.search(r"\b([PS]0\d{5})\b", title)
        return f"AIIB:{c}:{norm(n)[:80]}", (m.group(1) if m else ""), n
    if src in ("AfDB", "IsDB"):
        n = DOC_PREFIX.sub("", title)
        n = re.sub(r"\s*[-–]\s*(gpn|spn|eoi|ami|aoi)\s*$", "", n, flags=re.I)
        if src == "AfDB":
            n = re.sub(r"^[A-Za-z' ]+ - ", "", n, count=1)  # leading country name
        n = re.sub(r'\s*\((simplified|simplifie)\)|"', "", n, flags=re.I).strip(" -")
        return f"{src.upper()}:{c}:{norm(n)[:80]}", "", n
    return "", "", ""


# ---------------------------------------------------------------- event construction
COLS = ["event_id", "type", "tags", "change", "change_note", "event_date", "first_seen", "last_seen", "title", "summary",
        "project_country", "buyer_country", "supplier_country", "publisher_country", "affected_markets", "value_usd",
        "buyer", "supplier", "actors", "sector", "project_key", "project_ref", "link_basis", "tender_id", "record_id",
        "origin", "sources", "source_count", "independent_sources", "mirrors", "republished_count", "url",
        "status", "tender_deadline", "verified", "inferred", "what_changed", "why_matters", "sinder_angle", "confirm_by", "monitor_next",
        "tier", "content_hash"]
MATERIAL = ("title", "value_usd", "type", "tender_deadline", "status")


def ev(**kw):
    e = {c: "" for c in COLS}
    e.update({k: v for k, v in kw.items() if k in COLS or k.startswith("_")})
    e["content_hash"] = sha(*(kw.get(k, "") for k in MATERIAL))
    return e


def record_events(rows, wb_awards, awards, plans, t):
    """Events from official records. Returns (events, projects registry, name index)."""
    out, projects = [], {}
    name_ix = {}  # (country, norm name) -> project key ; ("*", norm name) too

    def reg(key, ref, name, country, **kw):
        p = projects.setdefault(key, {"key": key, "ref": ref, "name": name, "country": country, "buyer": "", "sector": "", "value_usd": 0,
                                      "status": "", "link": "", "board_date": ""})
        for k, v in kw.items():
            if v and not p.get(k):
                p[k] = v
        if name:
            name_ix.setdefault((country, norm(name)), key)
            name_ix.setdefault(("*", norm(name)), key)
        return p

    # World Bank pipeline / approved projects
    for r in rows:
        if not r.get("id", "").startswith("WBP-"):
            continue
        key, ref, name = mdb_project(r)
        nt = r.get("notice_type", "")
        status = "pipeline" if "Pipeline" in nt else "approved" if "Active" in nt else "dropped" if "Dropped" in nt else "closed" if "Closed" in nt else ""
        board = r.get("_pub", "")
        reg(key, ref, name, r["country"], buyer=r.get("buyer", ""), sector=r.get("sector", ""), value_usd=num(r.get("est_value_usd")),
            status=status, link=r.get("link", ""), board_date=board)
        projects[key]["status"] = status
        base = dict(project_country=r["country"], buyer_country=r["country"], publisher_country="INT", value_usd=int(num(r.get("est_value_usd"))) or "",
                    buyer=r.get("buyer", "")[:160], sector=r.get("sector", ""), project_key=key, project_ref=ref, link_basis="project id",
                    record_id=r["id"], origin="record", sources="World Bank Projects API", source_count=1, independent_sources=1,
                    url=r.get("link", ""), status=status, _dpf=bool(DPF.search(r.get("title_en", "") + " " + nt)))
        if status == "pipeline":
            out.append(ev(event_id="ev-" + sha(r["id"], "pipeline"), type="project_announcement", tags="world bank pipeline", _fb=True,
                          event_date=r.get("_first") or str(t), title=f"World Bank project in preparation: {name}"[:220],
                          summary=f"Expected board date {board or 'not stated'}; {nt}", **base))
        elif status == "approved":
            out.append(ev(event_id="ev-" + sha(r["id"], "approval"), type="financing_approval", tags="world bank", _fb=not (board and board <= str(t)),
                          event_date=board if board and board <= str(t) else (r.get("_first") or str(t)),
                          title=f"World Bank financing approved: {name}"[:220], summary=f"Board approval {board or 'date not stated'}; {nt}", **base))
        elif status == "dropped":
            out.append(ev(event_id="ev-" + sha(r["id"], "dropped"), type="project_dropped", tags="world bank", _fb=True,
                          event_date=r.get("_first") or str(t), title=f"World Bank project dropped: {name}"[:220], summary=nt, **base))

    # World Bank procurement plans
    for p in plans:
        pid = p.get("project_id", "")
        if not pid:
            continue
        m = re.search(r"P\d{6}-\s*(.*?)\s*-\s*Procurement Plan", p.get("title", ""))
        name = (m.group(1) if m else p.get("title", ""))[:160]
        key = f"WB:{pid}"
        reg(key, pid, name, p.get("country", ""))
        out.append(ev(event_id="ev-" + sha("wbplan", p.get("doc_id") or p.get("pdf")), type="planned_procurement", tags="procurement plan",
                      event_date=d10(p.get("date")) or str(t), title=f"Procurement plan published: {name}"[:220], summary=p.get("title", "")[:300],
                      project_country=p.get("country", ""), buyer_country=p.get("country", ""), publisher_country="INT", project_key=key, project_ref=pid,
                      link_basis="project id", record_id=f"WBPLAN-{p.get('doc_id', '')}", origin="record", sources="World Bank Documents",
                      source_count=1, independent_sources=1, url=p.get("pdf") or p.get("link", "")))

    # World Bank contract awards: register every project (for timelines), events only for >= $1M in the last 400 days
    cut = str(t - dt.timedelta(days=400))
    for a in wb_awards:
        pid = a.get("project_id", "")
        if not pid:
            continue
        key = f"WB:{pid}"
        reg(key, pid, a.get("project", ""), a.get("country", ""), sector=a.get("practice", ""))
        usd = num(a.get("usd"))
        if usd < 1e6 or d10(a.get("signed")) < cut:
            continue
        sup = a.get("supplier", "")[:120]
        out.append(ev(event_id="ev-" + sha("wbaward", pid, sup, a.get("signed"), a.get("description", "")[:60]), type="award", tags=a.get("category", "").lower(),
                      event_date=d10(a.get("signed")), title=f"{sup} signed {a.get('category', 'contract').lower()} contract: {a.get('description', '')}"[:220],
                      summary=f"{a.get('project', '')} ({pid}); method {a.get('method', '')}"[:300],
                      project_country=a.get("country", ""), buyer_country=a.get("country", ""), supplier_country=a.get("supplier_country", ""),
                      publisher_country="INT", value_usd=int(usd), supplier=sup, actors=sup, sector=a.get("practice", ""), project_key=key,
                      project_ref=pid, link_basis="project id", record_id=f"WBAW-{sha(pid, sup, a.get('signed'))}", origin="record",
                      sources="World Bank contract awards", source_count=1, independent_sources=1,
                      url=f"https://projects.worldbank.org/en/projects-operations/project-detail/{pid}", status="signed"))

    # planned rows and MDB open tenders from the tender chunks
    for r in rows:
        if r.get("id", "").startswith("WBP-"):
            continue
        src, st, nt = r.get("source", ""), r.get("stage", ""), r.get("notice_type", "")
        val = num(r.get("est_value_usd"))
        typ = ""
        if st == "planned":
            if src.startswith("MTender") and not re.search(r"plan", nt, re.I):
                continue  # direct awards and micro purchases are not pipeline projects
            typ = "expected_procurement_package" if re.search(r"sources sought|early market|request for information", nt, re.I) else "planned_procurement"
        elif src in MDB:
            typ = "tender_amendment" if AMEND.search(f"{r.get('title_en', '')} {nt}") else "tender_publication"
        elif val >= 1e8 and INTL.search(r.get("access", "")):
            typ = "tender_amendment" if AMEND.search(f"{r.get('title_en', '')} {nt}") else "tender_publication"
        if not typ:
            continue
        key, ref, name = mdb_project(r)
        if key:
            if key.startswith("WBN:"):  # an open WB notice: find the project id by name in the same country
                k2 = name_ix.get((r.get("country", ""), norm(name))) or name_ix.get(("*", norm(name)))
                if k2:
                    key, ref = k2, projects[k2]["ref"]
            reg(key, ref, name, r.get("country", ""), buyer=r.get("buyer", ""), sector=r.get("sector", ""), link=r.get("link", ""))
        out.append(ev(event_id="ev-" + sha(r["id"], typ), type=typ, tags=f"{src}; {nt}"[:80], _fb=not r.get("_pub"),
                      event_date=r.get("_pub") or r.get("_first") or str(t), title=(r.get("title_en") or r.get("title_original") or "")[:220],
                      summary=f"{src} {nt}; access: {r.get('access', '')}"[:300],
                      project_country=r.get("country", ""), buyer_country=r.get("country", ""), publisher_country="INT" if src in MDB else r.get("country", ""),
                      value_usd=int(val) or "", buyer=r.get("buyer", "")[:160], sector=r.get("sector", ""), project_key=key, project_ref=ref,
                      link_basis=("project id" if ref else "project name") if key else "", tender_id=r["id"], record_id=r["id"], origin="record",
                      sources=src, source_count=1, independent_sources=1, url=r.get("link", ""), tender_deadline=r.get("deadline", ""),
                      status=st, _stage=st, _days=r.get("days_left", ""), _access=r.get("access", ""), _buyer_n=norm(r.get("buyer", "")),
                      _toks=toks(r.get("title_en", "")), _score=num(r.get("score"))))

    # big awards (TED and national portals)
    for a in awards:
        usd = num(a.get("value_usd"))
        if usd < 1e8:
            continue
        w = a.get("winners", "")[:160]
        out.append(ev(event_id="ev-" + sha("award", a.get("link") or a.get("title"), w), type="award", tags=a.get("source", ""),
                      event_date=d10(a.get("published")), title=f"{a.get('buyer', '')[:60]} awarded: {a.get('title', '')}"[:220],
                      summary=f"Winners: {w}; bids {a.get('bids', '') or 'n/a'}"[:300], project_country=a.get("country", ""), buyer_country=a.get("country", ""),
                      supplier_country=a.get("winner_country", "").split(";")[0].strip(), publisher_country=a.get("country", ""), value_usd=int(usd),
                      buyer=a.get("buyer", "")[:160], supplier=w, actors=w, sector=a.get("group", ""), record_id="AW-" + sha(a.get("link")),
                      origin="record", sources=a.get("source", ""), source_count=1, independent_sources=1, url=a.get("link", ""),
                      status="awarded", _buyer_n=norm(a.get("buyer", "")), _toks=toks(a.get("title", ""))))
    return out, projects, name_ix


def news_items():
    items = []
    for r in _rows("briefing_items.csv"):
        items.append({"date": d10(r.get("date")), "title": r.get("title", ""), "summary": r.get("summary", ""), "source": r.get("source", ""),
                      "url": r.get("url", ""), "countries": (r.get("countries") or "").split(), "lead": r.get("lead_company", ""),
                      "group": r.get("group", ""), "topic": r.get("topic", "")})
    for r in _rows("news.csv"):
        items.append({"date": d10(r.get("date")), "title": r.get("title", ""), "summary": "", "source": r.get("domain", ""), "url": r.get("url", ""),
                      "countries": [], "lead": "", "group": "", "topic": "country press", "_qc": r.get("country", "")})
    return items


def news_events(items, t):
    """Type, enrich and dedup news. Returns (events, stats)."""
    typed, untyped = [], 0
    for it in items:
        title = re.sub(r"\s+-\s+[^-]{2,60}$", "", it["title"]).strip() if it["source"] and it["title"].endswith(it["source"]) else it["title"]
        summ = it["summary"].replace(it["source"], " ") if it["source"] else it["summary"]  # feed summaries end with the publisher name
        text = f"{title} {summ}"
        typ, tags = classify(title)
        if not typ:
            typ, tags = classify(text)
        if not typ:
            untyped += 1
            continue
        if typ == "supply_disruption" and MIL_STRIKE.search(title) and not re.search(r"\b(port|refinery|pipeline|terminal|plant|tanker|vessel|grid)\b", title, re.I):
            typ, tags = (tags[0], tags[1:]) if tags else ("", [])
            if not typ:
                untyped += 1
                continue
        cs = it["countries"] or countries_in(text)
        if not cs and it.get("_qc") and it["_qc"] in countries_in(text):
            cs = [it["_qc"]]
        sc = supplier_country(text, "")
        pc = next((c for c in cs if c != sc), cs[0] if cs else "")
        if pc == sc:
            sc = ""  # a domestic firm in its own market is not a foreign supplier
        aff = list(cs)
        for m in CHOKEPOINTS.finditer(text):
            aff.append(m.group(1).title())
        if typ in ("trade_policy_change", "material_price_logistics") and it["group"]:
            aff.append(it["group"])
        typed.append({"date": it["date"] or str(t), "title": title, "summary": it["summary"][:300], "source": it["source"], "url": it["url"],
                      "host": host_of(it["source"], it["url"]), "type": typ, "tags": tags, "pc": pc, "sc": sc, "cs": cs,
                      "aff": list(dict.fromkeys(aff)), "pub": publisher_country(it["source"], it["url"]), "actors": actors_in(title, it["lead"]),
                      "group": it["group"], "value": money_usd(text), "tk": title_key(title), "toks": toks(title)})
    typed.sort(key=lambda x: x["date"])
    clusters = []
    by_type = defaultdict(list)
    dup = mirror = indep = 0
    for x in typed:
        hit = None
        for c in reversed(by_type[x["type"]] + [c for c in clusters[-400:] if c["type"] != x["type"]]):
            gap = abs((dt.date.fromisoformat(x["date"]) - dt.date.fromisoformat(c["date"])).days)
            if gap > 10:
                continue
            j = jacc(x["toks"], c["toks"])
            same_title = x["tk"] == c["tk"] or j >= 0.8
            shared = bool(set(x["cs"]) & set(c["cs"])) or bool(set(x["actors"]) & set(c["actors"])) or (not x["cs"] and not c["cs"])
            if same_title or (c["type"] == x["type"] and shared and j >= 0.45):
                hit = (c, same_title); break
        if not hit:
            c = dict(x, hosts={x["host"]}, sources=[x["source"]], urls=[x["url"]], mirrors=0, independent=1, items=1)
            clusters.append(c); by_type[x["type"]].append(c)
            continue
        c, same_title = hit
        c["items"] += 1
        if x["host"] in c["hosts"]:
            dup += 1
        elif same_title:
            c["mirrors"] += 1; mirror += 1; c["hosts"].add(x["host"]); c["sources"].append(x["source"])
        else:
            c["independent"] += 1; indep += 1; c["hosts"].add(x["host"]); c["sources"].append(x["source"]); c["urls"].append(x["url"])
        c["value"] = c["value"] or x["value"]
        c["actors"] = list(dict.fromkeys(c["actors"] + x["actors"]))[:4]
        c["cs"] = list(dict.fromkeys(c["cs"] + x["cs"]))[:6]
        c["aff"] = list(dict.fromkeys(c["aff"] + x["aff"]))[:8]
        c["sc"] = c["sc"] or x["sc"]
    out = []
    for c in clusters:
        out.append(ev(event_id="ev-" + sha("news", c["type"], c["tk"], c["date"]), type=c["type"], tags=";".join(c["tags"]), event_date=c["date"],
                      title=c["title"][:220], summary=c["summary"], project_country=c["pc"], buyer_country=c["pc"] if c["type"] not in
                      ("trade_policy_change", "material_price_logistics") else "", supplier_country=c["sc"], publisher_country=c["pub"],
                      affected_markets=";".join(c["aff"]), value_usd=c["value"] or "", actors="; ".join(c["actors"]), sector=c["group"],
                      origin="news", sources="; ".join(dict.fromkeys(c["sources"]))[:240], source_count=c["items"],
                      independent_sources=c["independent"], mirrors=c["mirrors"], url=c["urls"][0], _toks=c["toks"], _tk=c["tk"]))
    return out, {"news_items": len(items), "untyped": untyped, "typed": len(typed), "clusters": len(clusters),
                 "same_host_duplicates": dup, "mirrored_copies": mirror, "independent_confirmations": indep}


# ---------------------------------------------------------------- linking
def link_buyer_title(events, projects):
    """planned row -> open tender, award -> planned/open notice: same country, same buyer, similar title."""
    ix = defaultdict(list)
    for e in events:
        if e["origin"] == "record" and e.get("_stage") in ("planned", "tender") and e.get("_buyer_n"):
            ix[(e["buyer_country"], e["_buyer_n"])].append(e)
    links = 0
    for e in events:
        if e["origin"] != "record" or e["project_key"] or not e.get("_buyer_n"):
            continue
        want = "planned" if e.get("_stage") == "tender" else None
        best, bj = None, 0.0
        for c in ix.get((e["buyer_country"], e["_buyer_n"]), []):
            if c is e or (want and c.get("_stage") != want) or (e.get("_stage") == "planned" and c.get("_stage") == "planned"):
                continue
            j = jacc(e["_toks"], c["_toks"])
            if j > bj:
                best, bj = c, j
        if best is None or bj < 0.45:
            continue
        anchor = e if e.get("_stage") == "planned" else best  # the planned row names the timeline when there is one
        key = best["project_key"] or f"T:{anchor['tender_id']}"
        if not best["project_key"]:
            best["project_key"], best["link_basis"] = key, "buyer + title"
            projects.setdefault(key, {"key": key, "ref": best["tender_id"], "name": best["title"][:160], "country": best["buyer_country"],
                                      "buyer": best["buyer"], "sector": best["sector"], "value_usd": num(best["value_usd"]), "status": "",
                                      "link": best["url"], "board_date": ""})
        e["project_key"], e["link_basis"] = key, f"buyer + title (j={bj:.2f})"
        links += 1
    return links


GENERIC_PROJ = toks("project program programme phase support development national improvement strengthening sector services system systems "
                    "infrastructure resilience emergency recovery additional financing climate sustainable integrated regional rural urban")


def link_news(events, projects):
    by_c = defaultdict(list)
    for p in projects.values():
        if p.get("name") and p.get("country"):
            by_c[p["country"]].append((p["key"], toks(p["name"]) - GENERIC_PROJ))
    links = 0
    for e in events:
        if e["origin"] != "news" or e["type"] in ("trade_policy_change", "material_price_logistics", "supply_disruption"):
            continue
        cs = [c for c in [e["project_country"]] + e["affected_markets"].split(";") if len(c) == 3 and c.isupper()]
        best, bs, bj = None, 0, 0.0
        nt = e["_toks"] - GENERIC_PROJ
        for c in dict.fromkeys(cs):
            for key, pt in by_c.get(c, []):
                sh = len(nt & pt)
                if sh >= 2:
                    j = jacc(nt, pt)
                    if (sh, j) > (bs, bj):
                        best, bs, bj = key, sh, j
        if best and (bs >= 3 or bj >= 0.3):
            e["project_key"], e["project_ref"], e["link_basis"] = best, projects[best]["ref"], f"name similarity ({bs} shared words, j={bj:.2f}) - inferred"
            links += 1
    return links


# ---------------------------------------------------------------- change detection
def change_detect(events, prev, t):
    """Mark new / updated / republished / seen against the previous events.csv; carry history."""
    ts = str(t)
    prev_by_id = {p["event_id"]: p for p in prev}
    prev_news = defaultdict(list)
    for p in prev:
        if p.get("origin") == "news":
            prev_news[p["type"]].append((p, toks(p["title"]), title_key(p["title"])))
    out, used = [], set()
    stats = Counter()
    for e in events:
        p = prev_by_id.get(e["event_id"])
        if p is None and e["origin"] == "news":
            for q, qt, qk in prev_news.get(e["type"], []):
                if q["event_id"] in used:
                    continue
                j = jacc(e["_toks"], qt)
                if qk == e.get("_tk") or j >= 0.8 or (j >= 0.6 and set(e["actors"].split("; ")) & set(q.get("actors", "").split("; ")) - {""}):
                    p = q; break
        if p is None:
            e.update(change="new", first_seen=ts, last_seen=ts, republished_count=0)
            stats["new"] += 1; out.append(e); continue
        used.add(p["event_id"])
        merged = dict(e)
        merged["event_id"], merged["first_seen"], merged["last_seen"] = p["event_id"], p.get("first_seen") or ts, ts
        rc = int(num(p.get("republished_count")))
        notes = []
        if e["origin"] == "news":
            old_src = set(filter(None, (p.get("sources") or "").split("; ")))
            new_src = [s for s in e["sources"].split("; ") if s and s not in old_src]
            later = e["event_date"] > (p.get("event_date") or "")
            merged["event_date"] = min(p.get("event_date") or e["event_date"], e["event_date"])
            merged["sources"] = "; ".join(list(old_src) + new_src)[:240]
            merged["independent_sources"] = max(int(num(p.get("independent_sources"))), int(num(e["independent_sources"])))
            merged["mirrors"] = int(num(p.get("mirrors"))) + int(num(e["mirrors"]))
            gap = (dt.date.fromisoformat(e["event_date"]) - dt.date.fromisoformat(p["event_date"])).days if p.get("event_date") else 0
            if later and gap > 3:
                rc += 1; ch = "republished"; notes.append(f"same announcement again {e['event_date']} (first {p['event_date']})")
            elif new_src and title_key(e["title"]) != title_key(p["title"]):
                merged["independent_sources"] = int(num(p.get("independent_sources"))) + len(new_src)
                ch = "updated"; notes.append(f"new independent source: {', '.join(new_src)[:80]}")
            elif new_src:
                merged["mirrors"] = int(num(p.get("mirrors"))) + len(new_src)
                ch = "seen"; notes.append("mirrored copy, not independent")
            else:
                ch = "seen"
            merged["title"] = p["title"]
        else:
            if e.get("_fb") and p.get("event_date"):
                merged["event_date"] = p["event_date"]  # a fallback date (first seen) must not drift forward run after run
            if p.get("content_hash") == e["content_hash"]:
                ch = "seen"
            else:
                diffs = [k for k in ("title", "value_usd", "type") if str(p.get(k, "")) != str(e.get(k, ""))]
                ch = "updated"; notes.append("changed: " + (", ".join(diffs) or "deadline or status"))
                if "value_usd" in diffs:
                    notes.append(f"value {p.get('value_usd') or 'n/a'} -> {e.get('value_usd') or 'n/a'}")
        merged.update(change=ch, change_note="; ".join(notes)[:200], republished_count=rc)
        stats[ch] += 1
        out.append(merged)
    keep_rec, keep_news = str(t - dt.timedelta(days=400)), str(t - dt.timedelta(days=180))
    out_ids = {e["event_id"] for e in out}
    for p in prev:
        if p["event_id"] in used or p["event_id"] in out_ids:
            continue
        lim = keep_news if p.get("origin") == "news" else keep_rec
        if (p.get("last_seen") or "") >= lim or (p.get("event_date") or "") >= lim:
            q = dict(p); q["change"] = "carried"
            q["_toks"] = toks(q.get("title", ""))
            out.append(q); stats["carried"] += 1
    return out, stats


# ---------------------------------------------------------------- analysis (templates, no model)
LABEL = {"project_announcement": "Project announced", "financing_approval": "Financing approved", "feasibility_permitting": "Feasibility / permitting step",
         "epc_selection": "EPC contractor selected", "planned_procurement": "Procurement planned", "tender_publication": "Tender published",
         "tender_amendment": "Tender amended", "award": "Contract awarded", "construction_start": "Construction started",
         "expected_procurement_package": "Procurement package expected", "supply_disruption": "Supply disruption",
         "trade_policy_change": "Trade-policy change", "material_price_logistics": "Price / logistics movement", "project_dropped": "Project dropped"}
WHY = {"project_announcement": "earliest signal of future packages; buyers and designers are still open to suppliers",
       "financing_approval": "money is committed, so goods and works packages usually follow within months",
       "feasibility_permitting": "the project is moving toward procurement; specs are being written now",
       "epc_selection": "the EPC contractor now buys the equipment and materials; sub-supply is open",
       "planned_procurement": "the buyer has listed the packages it will tender; timing and methods are known",
       "tender_publication": "a live procurement with a deadline", "tender_amendment": "scope, dates or terms changed on a live procurement",
       "award": "the winner now sources inputs; incumbents and prices become known",
       "construction_start": "site work begins; materials and equipment orders peak in the next months",
       "expected_procurement_package": "a buyer is sounding the market before a formal tender",
       "supply_disruption": "lead times and landed costs on affected routes or products can move",
       "trade_policy_change": "duties, eligibility or sanctions change the landed cost or who can supply",
       "material_price_logistics": "quotes and margins on affected materials or lanes may need repricing",
       "project_dropped": "planned packages will not come; remove from the pipeline"}
CONFIRM = {"project_announcement": "an official project record (MDB, ministry or regulator) with scope and budget",
           "financing_approval": "the lender's board record or signed financing agreement",
           "feasibility_permitting": "the permit or study award on the regulator's or buyer's site",
           "epc_selection": "the buyer's or contractor's own announcement or the award notice",
           "planned_procurement": "the plan document's package list and dates", "tender_publication": "the notice on the official portal",
           "tender_amendment": "the amendment text on the portal", "award": "the award notice on the official portal",
           "construction_start": "the contractor or buyer statement with site photos or dates",
           "expected_procurement_package": "a formal tender notice that follows",
           "supply_disruption": "carrier, port or operator notices; a second independent report",
           "trade_policy_change": "the official gazette, customs notice or sanctions list entry",
           "material_price_logistics": "the benchmark series (commodity_prices / price_trends) moving the same way",
           "project_dropped": "the lender's project page status"}
MONITOR = {"project_announcement": "financing approval, procurement plan or GPN", "financing_approval": "procurement plan, GPN and the first goods/works notices",
           "feasibility_permitting": "EPC tender or financing", "epc_selection": "the contractor's sub-supply tenders and site start",
           "planned_procurement": "the first tender notice from the plan", "tender_publication": "amendments, clarifications and the award",
           "tender_amendment": "the new deadline and the award", "award": "the winner's sub-supply needs and follow-on lots",
           "construction_start": "equipment and materials orders", "expected_procurement_package": "the formal tender",
           "supply_disruption": "duration and rerouting; freight rates", "trade_policy_change": "effective date, exemptions and retaliation",
           "material_price_logistics": "next month's benchmark move", "project_dropped": "a replacement project"}
FOCUS_SUPPLIERS = {"CHN", "IND", "TUR", "ISR", "KOR", "VNM"}


def analyse(e, timelines):
    from .regions import region
    from .dealfit import EMERGING
    typ = e["type"]
    reg_ = region(e["project_country"]) if e["project_country"] else ""
    tl = timelines.get(e["project_key"]) if e["project_key"] else None
    e["what_changed"] = f"{LABEL.get(typ, typ)} on {e['event_date']} ({e['change']}{': ' + e['change_note'] if e.get('change_note') else ''})"[:240]
    if e["origin"] == "record":
        e["verified"] = f"official record ({(e['sources'] or '')[:40]})"
    else:
        ind, mir = int(num(e["independent_sources"])), int(num(e["mirrors"]))
        e["verified"] = (f"corroborated by {ind} independent publishers" if ind >= 2 else "single report, unverified") + (f"; {mir} mirrored copies (not independent)" if mir else "")
    inf = []
    if e["origin"] == "news":
        inf.append("type and country roles read from the headline")
        if e["value_usd"]:
            inf.append("value parsed from text")
        if e["supplier_country"]:
            inf.append("supplier country from nationality words")
    if "inferred" in e.get("link_basis", "") or "j=" in e.get("link_basis", ""):
        inf.append("project link by " + e["link_basis"].split(" (")[0])
    if e.get("republished_count") and int(num(e["republished_count"])):
        inf.append(f"republished {e['republished_count']}x, not a new event")
    e["inferred"] = "; ".join(inf)
    val = f" (${num(e['value_usd']) / 1e6:,.0f}M)" if num(e["value_usd"]) >= 1e6 else ""
    e["why_matters"] = (WHY.get(typ, "") + val)[:240]
    if typ in ("trade_policy_change", "supply_disruption", "material_price_logistics"):
        hit = set(e["affected_markets"].split(";")) & (FOCUS_SUPPLIERS | {"ISR"})
        e["sinder_angle"] = (f"plausible: re-check landed cost and lead time on quotes touching {', '.join(sorted(hit))}" if hit
                             else "plausible: re-check quotes for the affected products or lanes" if typ != "trade_policy_change" or e["affected_markets"] else "none immediate")
    elif typ == "project_dropped":
        e["sinder_angle"] = "none: drop from watch lists"
    elif reg_ in EMERGING or (e["supplier_country"] in FOCUS_SUPPLIERS):
        stage = tl["stage"] if tl else ""
        e["sinder_angle"] = ("plausible (hypothesis): sub-supply to the winner" if typ in ("award", "epc_selection", "construction_start")
                             else "plausible (hypothesis): goods packages ahead" + (f"; timeline stage {stage}" if stage else ""))
    else:
        e["sinder_angle"] = "none immediate (outside focus markets)" if reg_ else "unclear: no country identified"
    e["confirm_by"] = CONFIRM.get(typ, "")
    e["monitor_next"] = MONITOR.get(typ, "")
    sc = {"financing_approval": 30, "epc_selection": 30, "award": 20, "construction_start": 25, "planned_procurement": 20, "tender_publication": 15,
          "trade_policy_change": 25, "supply_disruption": 20, "project_announcement": 15, "feasibility_permitting": 20, "material_price_logistics": 10,
          "expected_procurement_package": 10, "tender_amendment": 10, "project_dropped": 10}.get(typ, 5)
    v = num(e["value_usd"])
    sc += 30 if v >= 1e8 else 20 if v >= 2e7 else 10 if v >= 1e6 else 0
    sc += 15 if reg_ in EMERGING else 0
    sc += 10 if int(num(e["independent_sources"])) >= 2 else 0
    sc += 10 if e["project_key"] else 0
    sc -= 20 if (e["tags"] or "").startswith("SAM.gov") and v < 5e6 else 0
    e["tier"] = "high" if sc >= 60 else "medium" if sc >= 35 else "low"


# ---------------------------------------------------------------- timelines
STAGE_OF = {"project_announcement": 1, "feasibility_permitting": 2, "financing_approval": 3, "planned_procurement": 4, "expected_procurement_package": 4,
            "tender_publication": 5, "tender_amendment": 5, "epc_selection": 6, "award": 6, "construction_start": 7}
STAGE_NAME = {0: "", 1: "announced", 2: "feasibility/permitting", 3: "financing approved", 4: "procurement planned", 5: "tender open",
              6: "awarded", 7: "construction"}
TL_COLS = ["project_key", "project_ref", "name", "project_country", "buyer", "sector", "value_usd", "status", "stage", "n_events", "types",
           "first_date", "last_date", "financing_date", "board_date", "plan_date", "first_tender_date", "open_tenders", "open_tender_ids",
           "next_deadline", "n_awards", "award_value_usd", "top_winners", "winner_countries", "wb_awards_all", "wb_award_value_all",
           "goods_works_awards", "news_count", "milestones", "link"]


def build_timelines(events, projects, wb_awards, t):
    ts = str(t)
    by_p = defaultdict(list)
    for e in events:
        if e.get("project_key"):
            by_p[e["project_key"]].append(e)
    wb_all = defaultdict(lambda: [0, 0.0, 0])
    for a in wb_awards:
        if a.get("project_id"):
            x = wb_all[f"WB:{a['project_id']}"]
            x[0] += 1; x[1] += num(a.get("usd")); x[2] += a.get("category") in ("Goods", "Works")
    out = {}
    for key, evs in by_p.items():
        p = projects.get(key, {"ref": "", "name": evs[0]["title"], "country": evs[0]["project_country"], "buyer": evs[0]["buyer"], "sector": evs[0]["sector"],
                               "value_usd": 0, "status": "", "link": evs[0]["url"], "board_date": ""})
        evs.sort(key=lambda e: e["event_date"] or "")
        types = Counter(e["type"] for e in evs)
        stage = max((STAGE_OF.get(e["type"], 0) for e in evs), default=0)
        open_t = [e for e in evs if e["type"] in ("tender_publication", "tender_amendment") and e.get("change") != "carried"
                  and (not e.get("tender_deadline") or e["tender_deadline"] >= ts)]
        if stage == 5 and not open_t:
            stage = 4
        awards = [e for e in evs if e["type"] == "award"]
        win = Counter(); wc = Counter()
        for a in awards:
            for w in (a["supplier"] or "").split(";")[:3]:
                if w.strip():
                    win[w.strip()[:60]] += 1
            if a["supplier_country"]:
                wc[a["supplier_country"]] += 1
        fin = next((e["event_date"] for e in evs if e["type"] == "financing_approval"), "")
        plan = next((e["event_date"] for e in evs if e["type"] == "planned_procurement"), "")
        ft = next((e["event_date"] for e in evs if e["type"] in ("tender_publication", "tender_amendment")), "")
        wa = wb_all.get(key, [0, 0.0, 0])
        status = p.get("status") or ""
        out[key] = {"project_key": key, "project_ref": p.get("ref", ""), "name": (p.get("name") or "")[:160], "project_country": p.get("country", ""),
                    "buyer": (p.get("buyer") or "")[:120], "sector": p.get("sector", ""), "value_usd": int(num(p.get("value_usd"))) or "",
                    "status": status, "stage": "dropped" if status == "dropped" else STAGE_NAME[stage], "n_events": len(evs),
                    "types": ";".join(f"{k}:{v}" for k, v in types.most_common()), "first_date": evs[0]["event_date"], "last_date": evs[-1]["event_date"],
                    "financing_date": fin, "board_date": p.get("board_date", ""), "plan_date": plan, "first_tender_date": ft, "open_tenders": len(open_t),
                    "open_tender_ids": ";".join(e["tender_id"] for e in sorted(open_t, key=lambda e: -e.get("_score", 0) if isinstance(e.get("_score"), float) else 0)[:6]),
                    "next_deadline": min((e["tender_deadline"] for e in open_t if e.get("tender_deadline")), default=""),
                    "n_awards": len(awards), "award_value_usd": int(sum(num(a["value_usd"]) for a in awards)) or "",
                    "top_winners": "; ".join(w for w, _ in win.most_common(3)), "winner_countries": ";".join(c for c, _ in wc.most_common(4)),
                    "wb_awards_all": wa[0] or "", "wb_award_value_all": int(wa[1]) or "", "goods_works_awards": wa[2] or "",
                    "news_count": sum(1 for e in evs if e["origin"] == "news"),
                    "milestones": json.dumps([{"d": e["event_date"], "t": e["type"], "e": e["event_id"], "x": e["title"][:90]} for e in evs[-25:]], ensure_ascii=False),
                    "link": p.get("link") or evs[0]["url"]}
    return out


# ---------------------------------------------------------------- main
def build(write=True):
    t = today()
    rows = tender_rows()
    rec, projects, _ = record_events(rows, _rows("wb_awards.csv"), _rows("awards.csv"), _rows("wb_plans.csv"), t)
    news, nstats = news_events(news_items(), t)
    # identical record ids can appear in more than one chunk; one event per id
    seen, dedup_rec = set(), []
    for e in rec:
        if e["event_id"] in seen:
            continue
        seen.add(e["event_id"]); dedup_rec.append(e)
    rec_dups = len(rec) - len(dedup_rec)
    for e in dedup_rec + news:  # a source date in the future is a data error, not a forecast
        if (e["event_date"] or "") > str(t):
            e["summary"] = f"source date {e['event_date']} is in the future; {e['summary']}"[:300]
            e["event_date"] = str(t)
    events = dedup_rec + news
    l_bt = link_buyer_title(events, projects)
    l_news = link_news(events, projects)
    prev = _rows("events.csv")
    for p in prev:  # previous rows lack the private fields
        p.setdefault("_toks", toks(p.get("title", "")))
    events, cstats = change_detect(events, prev, t)
    wb_awards = _rows("wb_awards.csv")
    timelines = build_timelines(events, projects, wb_awards, t)
    for e in events:
        analyse(e, timelines)
    events.sort(key=lambda e: (e.get("event_date") or "", e.get("tier") == "high"), reverse=True)
    events = events[:9000]
    tl = sorted(timelines.values(), key=lambda x: (x["last_date"], num(x["value_usd"])), reverse=True)
    if write:
        with open(LEADS / "events.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore"); w.writeheader(); w.writerows(events)
        with open(LEADS / "project_timelines.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=TL_COLS, extrasaction="ignore"); w.writeheader(); w.writerows(tl)
    linked = sum(1 for e in events if e.get("project_key"))
    stats = {"events": len(events), "by_type": dict(Counter(e["type"] for e in events).most_common()), "by_origin": dict(Counter(e["origin"] for e in events)),
             "by_tier": dict(Counter(e.get("tier") for e in events)), "change": dict(cstats), "news": nstats, "record_id_duplicates": rec_dups,
             "linked_events": linked, "links_buyer_title": l_bt, "links_news_project": l_news, "timelines": len(tl),
             "timelines_multi_event": sum(1 for x in tl if x["n_events"] >= 2)}
    log.info("events: %s", json.dumps(stats))
    return events, tl, stats


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    _, _, s = build()
    print(json.dumps(s, indent=1))
