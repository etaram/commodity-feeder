"""Supplier Universe (A-tier): every company that won a public tender in the last 24 months, across all award
sources, with what it won, where, for whom, and the contact details published in the notices.
Output is private: data/private/universe.csv (git-ignored), pushed to the private Supplier Universe sheet."""
import csv
import json
import os
import re
from collections import defaultdict

from .common import AWARDS, DATA, LEADS, PRIVATE, log, today
from .contacts import clean_email, clean_phone, email_kind
from .regions import iso3, region
from .sectors import SECTORS, classify, _KW as SECTOR_KW
from .taxonomy import BY_ID, group_of_text

LEGAL = re.compile(r"\b(gmbh|ag|kg|sa|s\.a\.|sas|sarl|srl|s\.r\.l\.|spa|s\.p\.a\.|bv|nv|ltd|limited|llc|inc|plc|oy|ab|as|a/s|"
                   r"sp\. z o\.o\.|s\.r\.o\.|kft|d\.o\.o\.|ooo|tov|co\.?|corp|corporation|company|group|holding)\b")
GOODS = {"AGRI_FOOD", "ENERGY", "POWER", "MINING_METALS", "CHEMICALS", "TEXTILES", "CONSTR_MAT", "MACHINERY",
         "TRANSPORT_EQ", "DEFENCE", "HEALTH", "LAB", "ICT", "CONSUMER", "WATER"}
WORKS = {"BUILDING", "INFRA", "WATER", "ENGINEERING"}
NAME2ID = {v: k for k, v in SECTORS.items()}



# A company's main sector is what it is, not what it last won: (1) its declared industry or a name that says it
# (Leonardo, "... Defence Systems", "... Pharmaceuticals"); (2) otherwise the sector of the money it won, with the
# number of contracts as a smaller weight, so ten small consulting jobs do not outweigh one large defence contract.
# laundry, cleaning and catering firms: an on-site service, whatever their buyers (schools, hospitals) were
CLEANING_ID = re.compile(r"\b(laundry|laundries|linen|textile (rental|service)|workwear rental|vask\w*|w[äa]scherei|blanchisserie|"
                         r"lavander[ií]a|wasserij|tv[äa]tteri|pesula|pralnia|cleaning|rengøring|reinigung|nettoyage|limpieza|"
                         r"schoonmaak|facility services|facility management|catering|canteen)\b", re.I)
SERVICE_NAMES = {"Repair, maintenance & installation", "Transport & logistics services", "Engineering & architecture services",
                 "Consulting, business & financial services", "Environment, waste & cleaning", "Education, social & hospitality services"}
GOODS_HINT = re.compile(r"\b(manufactur\w*|producers?|factory|mill|supplier of|supplies of|equipment|machinery|vehicles|parts|spare|products?)\b", re.I)


NOT_SUPPLIER = re.compile(r"\b(world food programme|food and agriculture organi[sz]ation|international organi[sz]ation for migration|"
                          r"unicef|undp|unops|unhcr|unfpa|world health organi[sz]ation|united nations|red cross|red crescent|"
                          r"ministry of|ministerio de|minist[eè]re|government of|gobierno de|embassy of|municipality of|"
                          r"city council|county council)\b", re.I)
# insurers and green-area contractors read as what they are, whoever bought from them
INSURER_ID = re.compile(r"\b(seguros?|reaseguros|insurance|assurances?|versicherung\w*|assicurazion\w*|reinsurance)\b", re.I)
GREEN_ID = re.compile(r"\b(landscap\w*|paysag\w*|grounds maintenance|green areas?|espaces verts|jardin\w*|gardening|tree (works|surgery|care)|arborist)\b", re.I)


GUARD_ID = re.compile(r"\b(seguridad|guardian[ií]a|vigilancia|security services|guarding|gardiennage|bewachung)\b", re.I)


def service_only(r):
    """A company that only delivers services on site (laundry, cleaning, maintenance, consulting, design): not a
    cross-border goods supplier for Sinder, however much it won."""
    if r.get("type") == "goods supplier" or r.get("trader") == "yes" or r.get("hs_codes") or r.get("shipments_12m"):
        return False
    if CLEANING_ID.search(f"{r['supplier']} {r.get('web_title', '')} {r.get('industries', '')}"):
        return True
    return r.get("main_sector") in SERVICE_NAMES and (r.get("type") == "works/services" or not GOODS_HINT.search(f"{r.get('products', '')} {r.get('supplied', '')}"))


IDENTITY = [
    (re.compile(r"\b(defen[cs]e|military|armament|arms|ammunition|munitions|missile|ordnance|leonardo|rafael|elbit|thales|rheinmetall|"
                r"saab|bae systems|kongsberg|nexter|knds|chemring|krauss-?maffei|hensoldt|aselsan|roketsan|mbda|lockheed|raytheon|northrop|general dynamics|"
                r"patria|nammo|fn herstal|beretta|glock|sig sauer)\b", re.I), "DEFENCE"),
    (CLEANING_ID, "ENV_WASTE"),
    (INSURER_ID, "CONSULTING"),
    (GREEN_ID, "ENV_WASTE"),
    (re.compile(r"\b(pharma\w*|biotech\w*|medical devices?|diagnostics)\b", re.I), "HEALTH"),
    (re.compile(r"\b(steel|metals?|mining|aluminium|aluminum|copper)\b", re.I), "MINING_METALS"),
    (re.compile(r"\b(cement|ceramics?|glass|tiles)\b", re.I), "CONSTR_MAT"),
    (re.compile(r"\b(cables?|transformers?|switchgear|electric(al)?|solar|energy systems)\b", re.I), "POWER"),
    (re.compile(r"\b(telecom\w*|software|informatics|it solutions|ict)\b", re.I), "ICT"),
]
SERVICE_SECTORS = {"CONSULTING", "MAINT", "SOCIAL", "ENV_WASTE", "ENGINEERING", "LOGISTICS"}



def clean_products(t):
    """Customs product lines repeat fragments ("Stab, Stab Stab, Stab Stab Loose"): keep each distinct phrase once and
    drop a list that is only one short word repeated, which says nothing about what the company makes."""
    parts, seen = [], set()
    for p in re.split(r"\s*[,;]\s*", str(t or "")):
        k = " ".join(dict.fromkeys(p.lower().split()))
        if len(k) < 3 or k in seen or any(k in q for q in seen):
            continue
        seen.add(k); parts.append(p.strip())
    words = {w for p in parts for w in p.lower().split()}
    if len(words) <= 2 and all(len(w) <= 6 for w in words):
        return ""
    return ", ".join(parts)

GOODS_SECTORS = {"AGRI_FOOD", "ENERGY", "POWER", "MINING_METALS", "CHEMICALS", "TEXTILES", "CONSTR_MAT", "MACHINERY",
                 "TRANSPORT_EQ", "DEFENCE", "HEALTH", "LAB", "ICT", "CONSUMER", "WATER"}
_HSN = None


def hs_names(codes):
    """HS-4 heading descriptions for a supplier's customs codes (data/hs4.csv)."""
    global _HSN
    if _HSN is None:
        try:
            from .common import DATA
            _HSN = {r["hs4"]: r["description"] for r in csv.DictReader(open(DATA / "hs4.csv", encoding="utf-8"))}
        except OSError:
            _HSN = {}
    return "; ".join(dict.fromkeys(_HSN[h[:4]] for h in re.split(r"[\s,;]+", codes or "") if h[:4] in _HSN))


def self_sectors(text):
    """Sectors a company's own description names (its name, site title, about text, industry, customs headings).
    Every sector the text hits counts once; when it names goods, the service words in it (design, installation,
    events, training) are how it sells them, not what it is."""
    hits = [sec for sec, rx in SECTOR_KW if rx.search(text or "")]
    hits = list(dict.fromkeys(hits))
    goods = [h for h in hits if h in GOODS_SECTORS]
    return goods or hits


# when neither the contracts (reference numbers only) nor the company's own text name a sector, its name often does
NAME_HINT = [
    (re.compile(r"\b(consorcio|constructora|construcci\w*|constru[cç][aã]o|builders?|contractors?|edificaciones|obras)\b", re.I), "BUILDING"),
    (re.compile(r"\b(seguridad|guardian[ií]a|vigilancia|security services|guarding|seguran[cç]a)\b", re.I), "DEFENCE"),
    (re.compile(r"\b(tecnolog\w*|technolog\w*|telecom\w*|software|inform[aá]tica|sistemas|systems|digital|networks?|telconet)\b", re.I), "ICT"),
    (re.compile(r"\b(auto|autos|automotriz|motors?|veh[ií]culos|vehicles|camiones|trucks)\b", re.I), "TRANSPORT_EQ"),
    (re.compile(r"\b(farma\w*|pharma\w*|m[eé]dic\w*|medical|salud|health|hospital\w*|laboratorios?)\b", re.I), "HEALTH"),
    (re.compile(r"\b(agro\w*|alimentos|foods?|agr[ií]cola|av[ií]cola|l[aá]cteos)\b", re.I), "AGRI_FOOD"),
    (re.compile(r"\b(el[eé]ctric\w*|energ[ií]a|energy|power|solar)\b", re.I), "POWER"),
    (re.compile(r"\b(consult\w*|asesor\w*|advisory|auditor\w*)\b", re.I), "CONSULTING"),
    (re.compile(r"\b(ingenier[ií]a|ingegneria|engineering|engenharia)\b", re.I), "ENGINEERING"),
    (re.compile(r"\b(transport\w*|log[ií]stic\w*|cargo|freight)\b", re.I), "LOGISTICS"),
    (re.compile(r"\b(limpieza|cleaning|mantenimiento|maintenance)\b", re.I), "ENV_WASTE"),
]


REF_KIND = re.compile(r"^\s*\d{3,}/([GWCS])/(?:NCB|ICB|RFQ|RFP|QCBS|CQS|SSS|DC|NS|OT|LCS|FBS)\b", re.I)


def main_sectors(x, name, site_title="", about=""):
    """(sector, score) best first, and why the first one was chosen: identity (name or declared industry), the
    company's own description, or the contracts it won."""
    count, usd = x["sectors"], x.get("sec_usd", {})
    tot_c, tot_u = sum(count.values()) or 1, sum(usd.values()) or 0
    score = {k: 0.35 * count[k] / tot_c + (0.65 * usd.get(k, 0) / tot_u if tot_u else 0.65 * count[k] / tot_c) for k in count}
    why = {k: "contracts won" for k in score}
    ident = x.get("declared") or next((sec for rx, sec in IDENTITY if rx.search(f"{name} {x.get('industries', '')} {site_title if rx is CLEANING_ID else ''}")), "")
    if ident:
        score[ident] = score.get(ident, 0) + 1.5  # identity outranks any contract mix (which sums to at most 1)
        why[ident] = "declared industry" if x.get("declared") else "company name or industry"
    # what the company says it does: its name, site title, about text, industry and customs headings
    own = self_sectors(f"{name} {site_title} {about} {x.get('industries', '')} {hs_names(x.get('hs', ''))}")
    for i, sec in enumerate(own[:3]):
        # goods the company says it makes outrank the mix of what public buyers happened to buy from it
        score[sec] = score.get(sec, 0) + ((1.1 if sec in GOODS_SECTORS else 0.5) if i == 0 else 0.4)
        why.setdefault(sec, "own description")
        if why[sec] == "contracts won":
            why[sec] = "own description and contracts"
    if not score:
        hint = next((sec for rx, sec in NAME_HINT if rx.search(name)), "")
        if hint:
            score[hint] = 0.3; why[hint] = "name only (weak)"
    # a goods maker is not a consultancy because it also sold advice: a service sector leads only with a clear margin
    ranked = sorted(score.items(), key=lambda y: -y[1])
    if len(ranked) > 1 and ranked[0][0] != ident and ranked[0][0] in SERVICE_SECTORS and ranked[1][0] not in SERVICE_SECTORS and ranked[0][1] < ranked[1][1] * 1.5:
        ranked[0], ranked[1] = ranked[1], ranked[0]
    x["_sector_why"] = why.get(ranked[0][0], "") if ranked else ""
    # the company's own words point elsewhere than the chosen sector: listed for review in the check tab
    x["_sector_check"] = f"own description says {SECTORS.get(own[0], own[0])}" if own and ranked and own[0] != ranked[0][0] and own[0] in GOODS_SECTORS else ""
    return ranked

def norm(n):
    n = re.sub(r"[^\w ]", " ", (n or "").lower())
    n = LEGAL.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()[:80]


def _rates():
    try:
        from .run import _rates as r
        return r()
    except Exception:  # noqa: BLE001
        return {"USD": 1, "EUR": 1.08, "GBP": 1.27}


_GCACHE = {}


def _group(title):
    k = title[:160]
    if k not in _GCACHE:
        if len(_GCACHE) > 400_000:
            _GCACHE.clear()
        _GCACHE[k] = group_of_text(k)
    return _GCACHE[k]


def _item(title):
    parts = (title or "").split(" – ")
    if len(parts) >= 3:  # TED: "Country – CPV category – title" -> the English category
        title = parts[1]
    t = re.sub(r"\s+", " ", re.sub(r"^(supply|supplies|provision|procurement|purchase|acquisition|adquisici[oó]n|"
                                   r"suministro|fornecimento|aquisi[cç][aã]o|fourniture|achat|lieferung) (of|de|du|des|"
                                   r"von)?\s*", "", (title or "").strip(), flags=re.I)).strip(" .,-:;")
    return t[:70] if len(t) >= 4 else ""


def apply_refined(out):
    """The refined layer (leads/refine.py) on top of the built rows, before tiers and quality: the official website
    and its basis, the company's own-domain e-mails and site phones where the row has none, the role from the site,
    the duplicate group and its canonical record, and the open conflicts. The raw values are never lost: a replaced
    website is kept in website_rejected. REFINE=off skips this (rollback)."""
    import os
    for r in out:
        r.setdefault("website_basis", ""); r.setdefault("website_rejected", ""); r.setdefault("dup_of", ""); r.setdefault("refine", "")
        r.setdefault("identity", ""); r.setdefault("lei", ""); r.setdefault("legal_name", "")
        r.setdefault("founded", ""); r.setdefault("size_band", ""); r.setdefault("employees", r.get("employees", ""))
    if os.environ.get("REFINE", "on") == "off":
        return 0
    p = DATA / "checks" / "refine" / "refined.jsonl.gz"
    if not p.exists():
        return 0
    import gzip
    ref = {}
    for line in gzip.open(p, "rt", encoding="utf-8"):
        try:
            d = json.loads(line); ref[d["key"]] = d
        except (ValueError, KeyError):
            pass
    n = 0
    for r in out:
        d = ref.get(f"{r['supplier']}|{r['country']}")
        if not d:
            continue
        n += 1
        f = d.get("filled", {})
        rej = (d.get("cleaned") or {}).get("website")
        if rej and r.get("website") and rej.get("from", "").rstrip("/").lower().endswith(re.sub(r"^https?://(www\.)?", "", r["website"]).rstrip("/").lower()[:40]):
            r["website_rejected"] = f"{r['website']} ({rej.get('reason', '')})"; r["website"] = ""; r["website_source"] = ""
        if f.get("website"):
            if not r.get("website"):
                r["website"] = f["website"]["value"]; r["website_source"] = "refined"
            r["website_basis"] = f"{f['website']['basis']} ({f['website']['date']})"[:200]
        if not r.get("email") and f.get("emails_own_domain"):
            r["email"] = f["emails_own_domain"]["value"]; r["contact_level"] = r.get("contact_level") or "company website"
        if not r.get("phone") and f.get("phones_site"):
            r["phone"] = clean_phone(f["phones_site"]["value"].split(";")[0], r["country"])
        role = (f.get("role") or {}).get("value", "")
        if "manufacturer" in role and r.get("type") != "goods supplier" and not r.get("epc"):
            r["type"] = "goods supplier"
        elif role.startswith("trader") and r.get("trader") != "yes":
            r["trader"] = "yes"
        if f.get("identity"):  # only with a register record behind it (leads/registry_check.py)
            r["identity"] = f"{f['identity']['value']}: {f['identity']['basis']}"[:200]
        if f.get("lei"):
            r["lei"] = f["lei"]["value"]
        if f.get("legal_name"):
            r["legal_name"] = f["legal_name"]["value"][:150]
        # age and size the company states (leads/company_profile.py); contacts stay in the refined layer, not here
        if f.get("founded"):
            r["founded"] = f["founded"]["value"][:4]
        if f.get("size_band"):
            r["size_band"] = f"{f['size_band']['value']}: {f['size_band']['basis']}"[:120]
        if not r.get("employees") and f.get("employees"):
            r["employees"] = f["employees"]["value"].split(" ")[0]
        if not r.get("address") and f.get("registered_address"):
            r["address"] = f["registered_address"]["value"]
        dup = d.get("duplicate") or {}
        if dup and dup.get("canonical") and dup["canonical"] != d["key"]:
            r["dup_of"] = dup["canonical"]
        flags = []
        if d.get("conflicts"):
            flags.append(f"{len(d['conflicts'])} conflicts: " + "; ".join(d["conflicts"])[:160])
        if d.get("gaps"):
            flags.append("gaps: " + "; ".join(g.split(" (")[0] for g in d["gaps"])[:120])
        r["refine"] = f"{d.get('version')} {d.get('refined')} | " + " | ".join(flags) if flags else f"{d.get('version')} {d.get('refined')}"
    log.info("refined layer applied to %d suppliers", n)
    return n


def _described():
    """English description and role per checked company (leads/describe.py); empty when the layer has not run yet."""
    out = {}
    p = DATA / "describe" / "describe.jsonl.gz"
    if not p.exists():
        p = DATA / "checks" / "describe.jsonl.gz"   # the first run's place
    if p.exists():
        import gzip
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line); out[d["key"]] = d
                except (ValueError, KeyError):
                    pass
    return out


def _company_checks():
    """Latest company check per supplier key (leads/company_check.py), only where the site names the company."""
    out = {}
    p = DATA / "checks" / "company_checks.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("verdict") == "ok" and d.get("name_match") in ("high", "partial"):
                out[d.get("key")] = d
    return out


def _web_profiles():
    out = {}
    p = PRIVATE / "web_profiles.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            out[d.get("key")] = d
    return out


ROLES = [("Shipping line / shipowner", r"shipping|naviera|armador|maritime|ocean|sea transport|water transport|"
                                       r"vessel|tanker|bulk carrier|chartering|ship ?owner|marine transport|deep sea|lines?\b"),
         ("Port / terminal operator", r"\bports?\b|terminal|stevedor|harbou?r|puerto|porto\b"),
         ("Freight forwarder / customs broker", r"forward|nvocc|customs|transitaire|despachante|agente de carga|"
                                                r"freight services|cargo services|clearing|transportation arrangement"),
         ("Air cargo", r"air cargo|air freight|airline|aviation|481"),
         ("Trucking / road freight", r"truck|trucking|road transport|road freight|haulage|transporte de carga|484"),
         ("Rail freight", r"rail"),
         ("Warehousing / cold storage", r"warehous|storage|cold chain|almacen|armaz|493"),
         ("Courier / express", r"courier|express|parcel|postal|492"),
         ("Shipbuilding / ship repair", r"shipbuild|shipyard|ship repair|astillero|estaleiro|336611"),
         ("Logistics / 3PL", r"logistic|log[ií]stic|supply chain|3pl|transport")]
ROLES = [(n, re.compile(rx, re.I)) for n, rx in ROLES]


def logistics_role(text):
    for n, rx in ROLES:
        if rx.search(text):
            return n
    return ""


FREE_MAIL = re.compile(r"@(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|ukr|i\.ua|meta\.ua|bigmir|"
                       r"web\.de|orange|free|laposte|wanadoo|libero|terra|uol|bol|ig|rediffmail|qq|163|126|sina|naver|"
                       r"hanmail|proton|zoho|seznam|wp\.pl|o2|interia|abv|btinternet|sky|comcast|verizon|att|"
                       r"sbcglobal|prodigy|telkomsa|mweb|iafrica|vodamail|pec|legalmail|arubapec|postacert|pecimprese|cert\.legalmail|"
                       r"pec\.it|ticertifica|sicurezzapostale|gigapec|registerpec|t-online|mail\.ru|bk\.ru|list\.ru|inbox)\b", re.I)
GENERIC_SITE = re.compile(r"\b(pec\.it|legalmail\.it|arubapec\.it|postacert|gov\.|\.gov\b|europa\.eu|ted\.|linkedin\.|facebook\.|"
                          r"google\.|wikipedia\.|yellowpages|kompass|dnb\.com|bloomberg\.|zoominfo)", re.I)


def _fold(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(c))


def domain_matches(name, url):
    """True when the web domain plausibly belongs to the company: a word of the name (4+ letters, or its first 4)
    or the initials of the name appear in the domain. Rejects certified-mail and generic domains (pec.it,
    government or directory sites), so a buyer's or a mail provider's domain is not shown as the company's site."""
    host = re.sub(r"^https?://", "", _fold(url)).split("/")[0].removeprefix("www.")
    if not host or GENERIC_SITE.search(host):
        return False
    label = re.sub(r"[^a-z0-9]", "", ".".join(host.split(".")[:-1]) or host)
    words = [w for w in re.split(r"[^a-z0-9]+", _fold(norm(name))) if len(w) >= 3]
    if not words or not label:
        return False
    if any((len(w) >= 4 and (w in label or w[:4] in label)) or (len(w) == 3 and label.startswith(w)) for w in words):
        return True
    initials = "".join(w[0] for w in words)
    return len(initials) >= 2 and label.startswith(initials)


def _research_rows():
    """Suppliers the panel worker found and verified on the web (Supplier Universe tab 'Research Suppliers')."""
    try:
        from .push import UNIVERSE_SHEET, Sheets
        v = Sheets()._req("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{UNIVERSE_SHEET}/values/'Research Suppliers'!A1:L5000")
    except BaseException as e:  # noqa: BLE001  (no credentials locally, or the tab is missing)
        log.info("research suppliers not read: %s", str(e)[:120])
        return []
    vals = v.get("values") or []
    if len(vals) < 2:
        return []
    h = [x.strip() for x in vals[0]]
    rows = [dict(zip(h, r)) for r in vals[1:]]
    return [r for r in rows if r.get("supplier")]


def epc_class(x):
    """EPC / major works contractor: most of its public contracts are works, with a large volume or one large contract.
    'international' when it won works for buyers outside its home country."""
    if x.get("industries") and re.search(r"construction|engineering|epc|contract", str(x.get("industries")), re.I) and x.get("notable"):
        return "EPC / contractor"
    if x["works"] < max(1, x["wins"] / 2) or (x["works_usd"] < 20e6 and x["ex_usd"] < 10e6):
        return ""
    home = max(x["country"].items(), key=lambda y: y[1])[0] if x["country"] else ""
    intl = any(c and home and c != home for c in x["buyer_c"])
    return "International EPC" if intl else "EPC / major contractor"


def quality(r):
    """0-100: how strong a supplier looks from public evidence (value won, repeat wins, distinct buyers, exports,
    international lenders / foreign governments as buyers, notability)."""
    import math
    q = min(35, 5 * math.log10(1 + max(0, r["won_usd_est"])) - 10) if r["won_usd_est"] else 0
    q += min(20, 6 * math.log2(1 + r["wins"])) + min(15, 4 * math.log2(1 + r["buyers"]))
    q += 10 if r["exports"] else 0
    q += 8 if any(x in r["sources"] for x in ("World Bank", "USAspending", "UNGM", "UNDP", "AIIB", "EBRD")) else 0
    q += 12 if r["notable"] else 0
    q += 15 if "Research" in r["sources"] else (8 if "Wikidata products" in r["sources"] else 0)
    q += 5 if (r["email"] or r["phone"] or r["website"]) else 0
    sh = int(r.get("shipments_12m") or 0)
    q += min(30, 6 * math.log2(1 + sh)) if sh else (5 if r.get("hs_codes") else 0)  # steady exports to the US
    return round(max(0, min(100, q)))


def classification_check(out):
    """Review tab 'Classification check' in the private Supplier Universe sheet: per sector how many suppliers, how
    their sector was decided, how many are on-site service firms, how many the rule flags for review; then the top
    proven suppliers of every sector and every flagged one among them, so a wrong class is visible at a glance."""
    from .push import UNIVERSE_SHEET, Sheets
    by = defaultdict(lambda: defaultdict(int))
    for r in out:
        b = by[r["main_sector"] or "(none)"]
        b["total"] += 1; b["proven"] += r["tier"] in ("1", "2"); b["services"] += r["type"] == "works/services"
        b["goods"] += r["type"] == "goods supplier"; b["flagged"] += bool(r.get("sector_check"))
        b["why: " + (r.get("sector_why") or "-")] += 1
        b["email"] += bool(r["email"]); b["phone"] += bool(r["phone"]); b["website"] += bool(r["website"])
        b["no contact"] += not (r["email"] or r["phone"] or r["website"])
    whys = sorted({k for b in by.values() for k in b if k.startswith("why: ")})
    head = ["sector", "total", "proven (tier 1-2)", "goods", "services", "flagged", "email", "phone", "website", "no contact"] + whys
    rows = [[f"Built {today()}: {len(out):,} suppliers. 'why' = how the main sector was decided; 'flagged' = the company's own description names another goods sector."], head]
    for sec, b in sorted(by.items(), key=lambda y: -y[1]["total"]):
        rows.append([sec, b["total"], b["proven"], b["goods"], b["services"], b["flagged"], b["email"], b["phone"], b["website"], b["no contact"]] + [b.get(w, 0) for w in whys])
    cols = ["supplier", "country", "tier", "quality", "main_sector", "sector_why", "sector_check", "other_sectors", "type", "products", "supplied"]
    rows += [[""], ["Top proven suppliers per sector (check the class)"], cols]
    for sec in sorted(by):
        top = [r for r in out if (r["main_sector"] or "(none)") == sec and r["tier"] in ("1", "2")]
        top.sort(key=lambda r: -r["quality"])
        rows += [[str(r.get(c, ""))[:140] for c in cols] for r in top[:15]]
    flagged = sorted((r for r in out if r.get("sector_check") and r["tier"] in ("1", "2")), key=lambda r: -r["quality"])
    rows += [[""], [f"Flagged for review: {sum(1 for r in out if r.get('sector_check')):,} in all, the 300 strongest proven ones"], cols]
    rows += [[str(r.get(c, ""))[:140] for c in cols] for r in flagged[:300]]
    # the strongest proven goods suppliers the system cannot reach yet: the first ones to research for contacts
    gap = sorted((r for r in out if r["tier"] in ("1", "2") and r["type"] != "works/services" and not (r["email"] or r["phone"])),
                 key=lambda r: -r["quality"])
    rows += [[""], [f"Proven suppliers with no e-mail or phone: {len(gap):,}; the 300 strongest (website shown when known)"],
             ["supplier", "country", "tier", "quality", "main_sector", "website", "products"]]
    rows += [[str(r.get(c, ""))[:140] for c in ("supplier", "country", "tier", "quality", "main_sector", "website", "products")] for r in gap[:300]]
    Sheets().replace_tab(UNIVERSE_SHEET, "Classification check", rows, raw=True)
    log.info("classification check: %d sectors, %d flagged", len(by), sum(b["flagged"] for b in by.values()))


def balance_regions(rows):
    """Within each tier, interleave regions (best of Europe, best of Latin America, best of Africa, best of South Asia...)
    so the top of the list is not dominated by EU suppliers, whose public awards are larger and better documented.
    Rows of unknown region come later. Input must already be sorted by tier then quality."""
    import collections
    seen = collections.Counter()
    keyed = []
    for i, r in enumerate(rows):
        reg = r.get("region") or "unknown"
        seen[(r["tier"], reg)] += 1
        rr = seen[(r["tier"], reg)] * (4 if reg in ("unknown", "Other") else 1)
        keyed.append(((r["tier"], rr, i), r))
    return [r for _, r in sorted(keyed, key=lambda x: x[0])]


HS_SECTOR = [(1, 24, "AGRI_FOOD"), (25, 26, "MINING_METALS"), (27, 27, "ENERGY"), (28, 40, "CHEMICALS"), (41, 43, "TEXTILES"),
             (44, 46, "CONSTR_MAT"), (47, 49, "CONSUMER"), (50, 67, "TEXTILES"), (68, 70, "CONSTR_MAT"), (71, 83, "MINING_METALS"),
             (84, 84, "MACHINERY"), (85, 85, "POWER"), (86, 89, "TRANSPORT_EQ"), (90, 92, "LAB"), (93, 93, "DEFENCE"),
             (94, 97, "CONSUMER")]
NOISE = re.compile(r"\b\w*(xxx|email|fba|@|www|http|hs code|hscode|po no|invoice|container|pallets?|cartons?|pkgs?|"
                   r"packages?|bags?|ncm|ref|dthc|thc|caed|cargo|stow|sthe|request|carrying|temperature|degrees?|"
                   r"celsius|scac|shipper|freight|said|contain|stc|hbl|mbl|pcs|kgs?|net|gross|weight|total|demo|ecn|"
                   r"please|note|quantity|based|ocean|carrier|waybill|loaded|plts|payable|elsewhere|contract|lot|"
                   r"drums?|class|pgiii|hscd|psadav|xx+)\w*\b|\b\w*\d\w*\b", re.I)


def hs_sector(h):
    try:
        ch = int(str(h)[:2])
    except ValueError:
        return ""
    return next((sec for a, b, sec in HS_SECTOR if a <= ch <= b), "")


def _customs():
    """Foreign exporters that shipped to the US, from US Customs bills of lading (ImportYeti HS pages, cached by
    leads/importyeti.py): real producers and traders with product evidence (HS heading, goods described, shipments
    in the last 12 months). Freight forwarders are left out. One record per (name, country), merged over headings."""
    out = {}
    for f in sorted((LEADS / "importyeti").glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except ValueError:
            continue
        head = f.stem
        for r in d.get("records", []):
            if r.get("role") != "supplier" or r.get("forwarder") or not r.get("company"):
                continue
            k = (norm(r["company"]), iso3(r.get("country") or "") or "")
            if len(k[0]) < 3 or not k[1] or k[1] == "USA":
                continue
            x = out.setdefault(k, {"name": r["company"], "ship12": 0, "total": 0, "heads": {}, "products": [], "address": ""})
            x["ship12"] = max(x["ship12"], r.get("shipments_12m") or 0)  # the same shipments appear under each heading
            x["total"] = max(x["total"], r.get("total_shipments") or 0)
            own = [h.replace(".", "")[:4] for h in (r.get("hs_codes") or "").split() if h[:2].isdigit()]
            for i, h in enumerate(own or [head]):  # the company's own HS codes first, else the page's heading
                x["heads"][h] = x["heads"].get(h, 0) + (len(own) - i if own else 0.5)
            x["address"] = x["address"] or r.get("address") or ""
            p = re.sub(r"\s+", " ", NOISE.sub(" ", r.get("products") or "")).strip(" ,.-")
            if p and len(x["products"]) < 3:
                x["products"].append(p[:90])
    return out


TIER_NAMES = {"1": "Strategic", "2": "Proven", "3": "Qualified", "4": "Unproven"}


def supplier_tier(r):
    """Supplier tier 1-4 from public evidence of capacity and reach (independent of any single tender):
    1 Strategic - large and repeat public contracts (>= $10M won and 5+ wins, or >= $5M with cross-border sales),
                  or a notable producer that also wins public contracts
    2 Proven    - >= $1M won with 3+ wins, cross-border sales, or a notable producer / verified exporter
    3 Qualified - repeat winner (2+ wins) or >= $250K won, and reachable (contact or website)
    4 Unproven  - a single small award or thin data
    Returns (tier, reason)."""
    usd, wins = r["won_usd_est"] or 0, r["wins"] or 0
    cross = bool(r["exports"]) and "the US" not in r["exports"]  # customs exporters are tiered by shipments below
    notable = bool(r["notable"]) or "Wikidata products" in r["sources"]
    reach = bool(r["email"] or r["phone"] or r["website"])
    m = f"${usd / 1e6:.1f}M won, {wins} wins" if usd >= 1e6 else f"${usd / 1e3:.0f}K won, {wins} wins"
    if (usd >= 10e6 and wins >= 5) or (usd >= 5e6 and cross) or (notable and wins >= 3 and usd >= 1e6):
        return "1", f"Strategic: {m}" + (", sells abroad" if cross else "") + (", notable producer" if notable else "")
    if (usd >= 1e6 and wins >= 3) or cross or notable:
        return "2", f"Proven: {m}" + (", sells abroad" if cross else "") + (", notable producer" if notable else "")
    sh = int(r.get("shipments_12m") or 0)
    if sh >= 12:
        return "2", f"Proven: {sh} shipments to the US in 12 months (customs records)"
    if r.get("hs_codes"):
        return "3", f"Qualified: exporter in US customs records ({sh} shipments in 12 months)"
    if (wins >= 2 or usd >= 250e3) and reach:
        return "3", f"Qualified: {m}, reachable"
    return "4", f"Unproven: {m}" + ("" if reach else ", no contact yet")


def _awards():
    """(file, award row) from the public award files and the private external award datasets."""
    for f in sorted(AWARDS.glob("*.json")) + sorted(AWARDS.glob("*/*.json")):
        for a in json.loads(f.read_text()):
            yield f, a
    for f in sorted((PRIVATE / "awards_ext").glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    yield f, json.loads(line)
                except ValueError:
                    continue


SANCTIONS_COMPREHENSIVE = {"IRN", "SYR", "PRK", "CUB"}
SANCTIONS_SECTORAL = {"RUS", "BLR", "VEN", "MMR"}


PROVEN_GOODS = {"POWER", "ENERGY", "HEALTH", "DEFENCE", "ICT", "MACHINERY", "AGRI_FOOD", "MINING_METALS", "CHEMICALS",
                "CONSTR_MAT", "LAB", "TRANSPORT_EQ", "WATER"}
PROVEN_EPC = {"POWER", "ENERGY", "WATER"}
PROVEN_MIN_USD = 100_000   # one recent focus-sector award of at least this size makes a winner a listed (tier 3) supplier
PROVEN_DAYS = 730
PROVEN_MAX = 40_000  # bound on what the rule adds to the app's index per build (about +10% rows)
PROVEN_WEAK = {"Middle East & North Africa", "East Asia", "Sub-Saharan Africa", "Latin America"}
# a natural person (sole trader) is not listed as a proven supplier: Ukrainian/Russian patronymics, "FOP"
PERSON_NAME = re.compile(r"(^|\s)(ФОП|ФЛП|ІП|ИП)\s|\b[А-ЯІЇЄҐA-Z][а-яіїєґ'A-Za-z-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+(ович|евич|йович|івна|ївна|овна|евна|ична|ич)\b", re.I)


def focus_award(sec, svc_cpv):
    """A contract in a Sinder focus sector: goods (not a service or works CPV), or works in power, energy or water (EPC)."""
    return bool(sec) and ((sec in PROVEN_GOODS and not svc_cpv) or (sec in PROVEN_EPC and svc_cpv))


def evidence(a, share, folder=""):
    """The award behind 'proven': contract title, buyer and its country, date, the winner's share in USD, source, link."""
    link = a.get("link") or ""
    if not link and str(a.get("id", "")).startswith("TED-"):
        link = f"https://ted.europa.eu/en/notice/-/detail/{str(a['id'])[4:]}"
    return {"t": re.sub(r"\s+", " ", str(a.get("title") or ""))[:140], "b": str(a.get("buyer") or "")[:80],
            "c": (a.get("country") or "").split(",")[0][:3], "d": (a.get("published") or "")[:10], "u": round(share or 0),
            "s": str(a.get("source") or folder)[:40], "l": link[:200], "id": str(a.get("id") or "")[:80]}


def proven_text(ev):
    if not ev:
        return ""
    v = f", USD {ev['u']:,}" if ev.get("u") else ""
    return f"won: {ev['t']} ({ev['b']}, {ev['c']}, {ev['d']}{v}) [{ev['s']}{(' ' + ev['l']) if ev.get('l') else ''}; {ev['id']}]"[:640]


MANUF_NAME = re.compile(r"\b(manufactur\w*|fabricant\w*|fabrica\w*|f[áa]brica|factory|industr(?:y|ies|ial|ie|ia|ias|ieel)|"
                        r"mills?|werke?|kabelwerk\w*|steelworks|pharmaceutic\w*|pharma|laborat[oó]rios? farmac\w*|cement\w*|"
                        r"metallurg\w*|producers?|produ[cç][aã]o|manufaktur\w*|fertigung|завод|фабрика)\b", re.I)
TRADER_NAME = re.compile(r"\b(trading|traders?|imports?|importers?|exports?|exporters?|impex|import-export|distribu\w*|comercial\w*|"
                         r"comercializ\w*|handel\w*|handels\w*|n[ée]goce|supplies|suppliers?|general merchants?|wholesal\w*|"
                         r"commerce|merchandis\w*|торг\w*|постач\w*)\b", re.I)
EPC_TITLE = re.compile(r"supply,? (?:and|&) install|design,? (?:supply|build)|turn-?key|\bEPC\b|engineering,? procurement|"
                       r"construction of|construcci[oó]n de|travaux de|obras? de|Bauleistung|rehabilitation of|installation works", re.I)


def award_role(name, works, wins, epc="", trader=False, role_read="", title=""):
    """(role, basis) from the award record and the name; the website check refines it later. A role from the
    company's own website wins; otherwise works contracts make it a contractor, then the name decides."""
    if role_read in ("manufacturer", "producer"):
        return "manufacturer", "its website (read by the website check)"
    if role_read == "trader":
        return "trader / distributor", "its website (read by the website check)"
    if epc:
        return "EPC / contractor", f"{epc}: {works} of {wins} contracts are works"
    if wins and works >= max(1, wins / 2):
        return "EPC / contractor", f"{works} of {wins} contracts are works"
    m = MANUF_NAME.search(name or "")
    if m:
        return "manufacturer", f"company name says '{m.group(0)}' (to confirm on its website)"
    m = TRADER_NAME.search(name or "")
    if m or trader:
        return "trader / distributor", f"company name says '{m.group(0)}'" if m else "listed as a trader"
    if EPC_TITLE.search(title or ""):
        return "EPC / contractor", "the award is a supply-and-install or works contract"
    return "supplier (role to confirm)", "goods awards only; the website check will tell manufacturer or trader"


def _dom(u):
    h = re.sub(r"^https?://", "", (u or "").lower()).split("/")[0].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def promote_proven(out):
    """Winners with one recent focus-sector award of PROVEN_MIN_USD or more are listed (tier 3) even before a contact is
    found: the award is the proof, and the website check and the enrichment are queued for them. Not when the record
    is a natural person, or a duplicate of a listed record (same legal id, or same website domain in the same
    country). Returns counts."""
    listed_ids, listed_doms = set(), set()
    for r in out:
        if r["tier"] in ("1", "2", "3"):
            if r.get("legal_id"):
                listed_ids.add(re.sub(r"\W", "", str(r["legal_id"])).upper())
            if _dom(r.get("website")):
                listed_doms.add((_dom(r["website"]), r["country"]))
    n = {"promoted": 0, "duplicate_legal_id": 0, "duplicate_domain": 0, "person": 0, "over_cap": 0}
    cands = [r for r in out if r["tier"] == "4" and r.get("origin") == "A" and float(r.get("proven_focus_usd") or 0) >= PROVEN_MIN_USD]
    # weak regions first, then the size of the proving award; at most PROVEN_MAX listed per build (index size)
    cands.sort(key=lambda r: (r.get("region") not in PROVEN_WEAK, -float(r.get("proven_focus_usd") or 0)))
    for r in cands:
        if n["promoted"] >= PROVEN_MAX:
            n["over_cap"] += 1; continue
        if PERSON_NAME.search(r["supplier"]):
            n["person"] += 1; continue
        lid = re.sub(r"\W", "", str(r.get("legal_id") or "")).upper()
        if lid and lid in listed_ids:
            n["duplicate_legal_id"] += 1; r["dup_hint"] = "same legal id as a listed supplier"; continue
        if _dom(r.get("website")) and (_dom(r["website"]), r["country"]) in listed_doms:
            n["duplicate_domain"] += 1; r["dup_hint"] = "same website as a listed supplier"; continue
        reach = bool(r.get("email") or r.get("phone") or r.get("website"))
        r["tier"] = "3"
        r["tier_reason"] = (f"Qualified: proven by award (USD {float(r['proven_focus_usd']) / 1e3:,.0f}K, {r.get('wins')} win"
                            f"{'s' if str(r.get('wins')) != '1' else ''})" + ("" if reach else ", contact being found"))
        n["promoted"] += 1
        if lid:
            listed_ids.add(lid)
        if _dom(r.get("website")):
            listed_doms.add((_dom(r["website"]), r["country"]))
    return n


def build():
    rates = _rates()
    proven_since = str(today() - __import__("datetime").timedelta(days=PROVEN_DAYS))
    sup = defaultdict(lambda: {"names": defaultdict(int), "country": defaultdict(int), "wins": 0, "usd": 0.0,
                               "sectors": defaultdict(int), "sec_usd": defaultdict(float), "cpv": defaultdict(int), "buyer_c": set(), "buyers": set(),
                               "last": "", "first": "9999", "sources": set(), "example": "", "ex_usd": 0,
                               "email": "", "phone": "", "website": "", "address": "", "legal_id": "", "goods": 0, "works": 0,
                               "works_usd": 0.0,
                               "groups": defaultdict(int), "items": {}})
    n_aw = 0
    for f, a in _awards():
        if True:
            if a.get("empty") or not a.get("winners"):
                continue
            n_aw += 1
            wcs = [x.strip() for x in (a.get("winner_country") or "").split(",") if x.strip()]
            v, c = a.get("value"), a.get("currency")
            usd = v * rates.get(c, 0) if isinstance(v, (int, float)) and c in rates else 0
            usd = usd if 0 < usd < 2e9 else 0
            share = usd / max(1, len(a["winners"]))
            for i, w in enumerate(a["winners"]):
                k = norm(w)
                if len(k) < 3:
                    continue
                wc = iso3(wcs[i] if i < len(wcs) else (wcs[0] if wcs else "")) or ""
                x = sup[(k, wc)]
                x["names"][w] += 1; x["country"][wc] += 1; x["wins"] += 1; x["usd"] += share
                sec = a.get("sector") or NAME2ID.get(a.get("sector_name", ""), "")
                if not sec and i == 0:  # an award file without a sector: read it from the contract title and its codes
                    sec = classify(a.get("title") or "", (a.get("cpv") or "").split()[:1] or None)[0]
                    a["sector"] = sec  # the other winners of the same award reuse it
                # CPV 45 is works and 50-98 are services (health and social work 85, repair 50, cleaning 90 ...):
                # such a contract is not goods, whatever sector it falls in
                cpv2 = re.sub(r"\D", "", (a.get("cpv") or "").split(" ")[0])[:2]
                svc_cpv = cpv2.isdigit() and (cpv2 == "45" or int(cpv2) >= 50)
                if sec:
                    x["sectors"][sec] += 1; x["sec_usd"][sec] += share
                    x["goods"] += 1 if sec in GOODS and not svc_cpv else 0
                elif REF_KIND.search(a.get("title") or ""):
                    # East African PPDA reference numbers carry the procurement kind: /G/ goods, /W/ works, /C/ or /S/ consultancy
                    # and services. The sector stays unknown, but the kind is on record.
                    k = REF_KIND.search(a.get("title") or "").group(1).upper()
                    if k == "G":
                        x["goods"] += 1
                    elif k == "W":
                        x["works"] += 1; x["works_usd"] += share
                if sec in WORKS or str(a.get("nature", "")).lower().startswith("works"):
                    x["works"] += 1; x["works_usd"] += share
                g = a.get("group") or _group(a.get("title") or "")
                if g:
                    x["groups"][g] += 1
                if a.get("naics"):
                    x["naics"] = a["naics"]
                it = _item(a.get("title") or "")
                if it and (it in x["items"] or len(x["items"]) < 8):
                    x["items"][it] = x["items"].get(it, 0) + 1
                for cp in (a.get("cpv") or "").split()[:1]:
                    x["cpv"][cp[:8]] += 1
                x["buyer_c"].add((a.get("country") or "").split(",")[0]); x["buyers"].add(norm(a.get("buyer")))
                p = a.get("published") or ""
                x["last"] = max(x["last"], p); x["first"] = min(x["first"], p or "9999")
                x["sources"].add(a.get("source") or f.parent.name)
                if share >= x["ex_usd"]:
                    x["ex_usd"] = share; x["example"] = f"{a.get('title', '')[:120]} ({a.get('buyer', '')[:60]}, {p})"
                # award evidence for the proven-supplier layer: the largest recent award in a Sinder focus sector
                # (goods, or EPC works in power, energy and water), with its source and link
                if p >= proven_since and (share >= x.get("pf", -1)) and focus_award(sec, svc_cpv):
                    x["pf"] = share
                    x["pf_ev"] = evidence(a, share, f.parent.name)
    # contacts captured from notices (private cache)
    n_ct = 0
    for f in PRIVATE.glob("contacts_*.jsonl"):
        uniq = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            uniq[(c.get("name"), c.get("email"), c.get("phone"), c.get("legal_id"))] = c
        f.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in uniq.values()), encoding="utf-8")
        for c in uniq.values():
            k = (norm(c.get("name")), iso3(c.get("country") or "") or "")
            x = sup.get(k) or next((sup[kk] for kk in ((k[0], ""),) if kk in sup), None)
            if not x:
                continue
            n_ct += 1
            for fld in ("email", "phone", "website", "address", "legal_id"):
                if c.get(fld) and not x[fld]:
                    x[fld] = c[fld]
    # tier B: notable producers and traders (Wikidata), merged with award winners when the name matches
    notable = {}
    for f in [*(LEADS / "companies" / "wikidata").glob("[A-Z][A-Z][A-Z].json"),
              *(LEADS / "companies" / "listed").glob("[A-Z][A-Z][A-Z].json")]:
        d = json.loads(f.read_text())
        for c in d.get("companies", []):
            notable[(norm(c["name"]), d["country"])] = c
    n_b = 0
    for k, c in notable.items():
        x = sup.get(k)
        if x is None:
            x = sup[k]; x["names"][c["name"]] += 1; x["country"][k[1]] += 1; x["tier_b"] = True; n_b += 1
            if c.get("sector"):
                x["sectors"][c["sector"]] += 1; x["declared"] = c["sector"]
                x["goods"] += 1 if c["sector"] in GOODS else 0
            x["sources"].add("Wikidata listed" if c.get("listed_on") else "Wikidata")
        x["website"] = x["website"] or c.get("website", "")
        x["industries"] = c.get("industries", ""); x["employees"] = c.get("employees", "")
        x["products"] = c.get("products", "")
        x["trader"] = c.get("trader", False); x["notable"] = True
    # commodity producers by product (Wikidata) and suppliers found by the panel's research worker
    n_p = n_r = 0
    pf = LEADS / "companies" / "products.json"
    extra = []
    if pf.exists():
        for c in json.loads(pf.read_text()).get("companies", []):
            extra.append(("Wikidata products", c["name"], c.get("country", ""), {
                "products": ", ".join(c.get("products", [])), "website": c.get("website", ""),
                "industries": "; ".join(c.get("industries", []))}))
    for c in _research_rows():
        extra.append(("Research", c["supplier"], c["country"], c))
    for src, name, ctry, c in extra:
        k = (norm(name), iso3(ctry) or "")
        if len(k[0]) < 3:
            continue
        x = sup.get(k)
        if x is None:
            x = sup[k]; x["names"][name] += 1; x["country"][k[1]] += 1; x["tier_b"] = True
            sec = classify(f"{c.get('products', '')} {c.get('industries', '')}")[0]
            if sec:
                x["sectors"][sec] += 1; x["goods"] += 1 if sec in GOODS else 0
        n_p += src != "Research"; n_r += src == "Research"
        x["sources"].add(src); x["notable"] = True
        prods = ", ".join(p for p in [x.get("products", ""), c.get("products", "")] if p)
        x["products"] = ", ".join(dict.fromkeys(p.strip() for p in prods.split(",") if p.strip()))[:300]
        for f_ in ("website", "email", "phone", "address"):
            if c.get(f_) and not x[f_]:
                x[f_] = c[f_]
        if c.get("industries") and not x.get("industries"):
            x["industries"] = c["industries"]
        if c.get("type") == "trader":
            x["trader"] = True
    # exporters seen in US customs records (bills of lading): adds producers in Asia and elsewhere with no public awards
    n_cu = 0
    for k, c in _customs().items():
        x = sup.get(k)
        if x is None:
            x = sup[k]; x["names"][c["name"]] += 1; x["country"][k[1]] += 1; x["tier_b"] = True; n_cu += 1
        x["sources"].add("US customs")
        x["ship12"] = c["ship12"]; x["ship_total"] = c["total"]
        heads = sorted(c["heads"].items(), key=lambda y: -y[1])
        x["hs"] = " ".join(h for h, _ in heads[:6])
        for h, _ in heads[:3]:
            sec = hs_sector(h)
            if sec:
                x["sectors"][sec] += 1; x["goods"] += 1 if sec in GOODS else 0
            g = next((gid for gid, gg in BY_ID.items() if h[:2] in (gg.get("hs") or [])), None)
            if g:
                x["groups"][g] += 1
        if c["products"]:
            prods = ", ".join(p for p in [x.get("products", ""), *c["products"]] if p)
            x["products"] = prods[:300]
        x["address"] = x["address"] or c["address"]
    # private data drops (leads/importer.py: sealed files the user handed over, such as a country directory).
    # Duplicates: the same normalised name in the same country, the local-script name, or the same website domain
    # all merge into one record; nothing is overwritten, only empty fields are filled.
    n_im_new = n_im_merged = 0
    try:
        from .importer import rows as import_rows
        drops = import_rows()
    except Exception as e:  # noqa: BLE001
        log.warning("imports skipped: %s", e); drops = []
    if drops:
        SHARED = re.compile(r"(^|\.)(alibaba|1688|made-in-china|indiamart|tradeindia|exportersindia|globalsources|ec21|go4worldbusiness|justdial|infoline|corporatedir|zaubacorp|"
                            r"chemicalregister|facebook|linkedin|instagram|twitter|x|youtube|google|sites\.google|wix|wixsite|blogspot|wordpress|weebly|"
                            r"yellowpages|kompass|europages|dnb|zoominfo|gmail|yahoo|hotmail|outlook|qq|163|126|sina)\.", re.I)

        def _dom(u):
            h = re.sub(r"^https?://", "", (u or "").lower()).split("/")[0].split(":")[0]
            h = h[4:] if h.startswith("www.") else h
            return "" if not h or "." not in h or SHARED.search(h + ".") or h in crowded else h  # a marketplace or a free host is not one company

        # a host given for more than 3 different names in the drops is a directory or a group site, not an identity
        _hn = defaultdict(set)
        for c in drops:
            hh = re.sub(r"^https?://", "", (c.get("website") or "").lower()).split("/")[0].split(":")[0]
            if hh:
                _hn[hh[4:] if hh.startswith("www.") else hh].add(norm(c.get("supplier")))
        crowded = {h for h, ns in _hn.items() if len(ns) > 3}
        GENERIC = {"group", "international", "industries", "industry", "chemical", "chemicals", "company", "trading", "exports", "export", "global",
                   "enterprises", "enterprise", "india", "china", "corporation", "holdings", "technology", "technologies", "products", "foods", "agro"}

        def _same_firm(a, b):
            """Same website is the same company only when the names also share a distinctive word (subsidiaries share a group site)."""
            ta = {w for w in norm(a).split() if len(w) > 2 and w not in GENERIC}
            tb = {w for w in norm(b).split() if len(w) > 2 and w not in GENERIC}
            return bool(ta & tb) or not ta or not tb
        by_dom, by_name, by_dom_any = {}, {}, {}
        for kk, xx in sup.items():
            if _dom(xx.get("website")):
                by_dom.setdefault((_dom(xx["website"]), kk[1]), kk); by_dom_any.setdefault(_dom(xx["website"]), kk)
            # a row with no country matches the record of that name that has won the most (its home record)
            if kk[0] not in by_name or xx.get("wins", 0) > sup[by_name[kk[0]]].get("wins", 0):
                by_name[kk[0]] = kk
        for c in drops:
            cty = iso3(c.get("country") or "") or ""
            keys = [(norm(c.get("supplier")), cty), (norm(c.get("name_local")), cty)]
            k = next((kk for kk in keys if len(kk[0]) >= 2 and kk in sup), None)
            if not k and _dom(c.get("website")) and (_dom(c["website"]), cty) in by_dom:
                cand = by_dom[(_dom(c["website"]), cty)]
                k = cand if _same_firm(c.get("supplier"), cand[0]) else None
            if not k and not cty:  # country not stated: the same name or the same website anywhere
                k = by_name.get(keys[0][0])
                if not k and _dom(c.get("website")) and by_dom_any.get(_dom(c["website"])) and _same_firm(c.get("supplier"), by_dom_any[_dom(c["website"])][0]):
                    k = by_dom_any[_dom(c["website"])]
            if not k:
                k = keys[0] if len(keys[0][0]) >= 2 else keys[1]
                if len(k[0]) < 2:
                    continue
                if not cty and c.get("country_hint"):
                    cty = iso3(c["country_hint"]) or ""; k = (k[0], cty)
                x = sup[k]; x["names"][c["supplier"]] += 1; x["country"][cty] += 1; x["tier_b"] = True; n_im_new += 1
                # a record made from one drop is found again by the next drop (same name or same website)
                if k[0] not in by_name:
                    by_name[k[0]] = k
                if _dom(c.get("website")):
                    by_dom.setdefault((_dom(c["website"]), cty), k); by_dom_any.setdefault(_dom(c["website"]), k)
                sec = classify(f"{c.get('products', '')} {c.get('industry', '')}")[0]
                if sec:
                    x["sectors"][sec] += 1; x["goods"] += 1 if sec in GOODS else 0
            else:
                x = sup[k]; n_im_merged += 1
            x["sources"].add(c.get("source") or "Import")
            if c.get("notable"):
                x["notable"] = True
            if c.get("name_local") and not x.get("name_local"):
                x["name_local"] = c["name_local"]
            if c.get("products"):
                prods = ", ".join(p for p in [x.get("products", ""), c["products"]] if p)
                x["products"] = ", ".join(dict.fromkeys(p.strip() for p in prods.split(",") if p.strip()))[:300]
            if c.get("industry") and not x.get("industries"):
                x["industries"] = c["industry"]
            if c.get("employees") and not x.get("employees"):
                x["employees"] = str(c["employees"])
            for f_ in ("website", "email", "phone", "address"):
                if c.get(f_) and not x[f_]:
                    x[f_] = c[f_]
                    if f_ == "website":
                        x["_site_given"] = True  # from the drop's own source page: kept even when the name is in another script
            if c.get("commodities"):
                x["import_commodities"] = c["commodities"]
            if c.get("province") and not x.get("province"):
                x["province"] = c["province"]
        log.info("imports: %d rows, %d new suppliers, %d merged into existing ones", len(drops), n_im_new, n_im_merged)
    web = _web_profiles()
    checks = _company_checks()
    described = _described()
    out = []
    for (k, wc), x in sup.items():
        name = max(x["names"].items(), key=lambda y: y[1])[0]
        if NOT_SUPPLIER.search(name):
            continue  # UN agencies, ministries, councils: buyers or implementers, not suppliers
        wp = web.get(f"{name[:120]}|{wc}") or {}
        ck = checks.get(f"{name[:120]}|{wc}")
        if ck:  # a checked site that names the company outranks the light profile: its own description and product headings
            own = "; ".join([ck.get("description") or ""] + (ck.get("products") or [])[:12]).strip("; ")
            dsc = described.get(f"{name[:120]}|{wc}")
            if dsc and dsc.get("mt") == "argos" and dsc.get("about_en"):
                own = dsc["about_en"]  # the site's own words in English (leads/describe.py, open-source translation): searchable and readable
            if dsc and dsc.get("role") in ("manufacturer", "producer", "trader"):
                x["_role_read"] = dsc["role"]
            wp = {**wp, "website": ck.get("website") or wp.get("website", ""), "title": ck.get("title") or wp.get("title", ""),
                  "about": own or wp.get("about", ""), "discovered": wp.get("discovered") or ck.get("name_match") == "high",
                  "email": wp.get("email") or "; ".join(e["email"] for e in (ck.get("emails") or []) if e.get("kind") == "generic")[:120],
                  "phone": wp.get("phone") or (ck.get("phones") or [""])[0]}
            x["_checked"] = ck.get("checked", "")
        site_src = "registry/notice" if x["website"] else ""
        if x["website"] and not x.get("_site_given") and not domain_matches(name, x["website"]):
            x["website"], site_src = "", ""  # a notice's website that is not the company's own (buyer, mail provider)
        if not x["website"] and wp.get("website"):
            if wp.get("discovered") or domain_matches(name, wp["website"]):
                x["website"] = wp["website"]; site_src = "found (name verified)" if wp.get("discovered") else "e-mail domain (name matches)"
        elif not x["website"] and x["email"] and "@" in x["email"] and not FREE_MAIL.search(x["email"]):
            dom = "http://" + x["email"].split(";")[0].strip().split("@")[1] + "/"
            if domain_matches(name, dom):
                x["website"] = dom; site_src = "e-mail domain (name matches)"
        if not x["email"] and wp.get("email"):
            x["email"] = wp["email"]
        if not x["phone"] and wp.get("phone"):
            x["phone"] = wp["phone"]
        # one clean e-mail list; phones in +<code><number> form so WhatsApp and call buttons work
        x["email"], x["phone"] = clean_email(x["email"]), clean_phone(x["phone"], wc)
        about = x.get("products") or wp.get("about") or ""
        items = "; ".join(i for i, _ in sorted(x["items"].items(), key=lambda y: -y[1])[:3])
        secs = main_sectors(x, name, wp.get("title") or "", about)
        out.append({
            "supplier": name[:120], "country": wc, "region": region(wc) if wc else "",
            "tier": "", "notable": "yes" if x.get("notable") else "",
            "trader": "yes" if x.get("trader") else "", "industries": x.get("industries", ""),
            "employees": x.get("employees", ""),
            "wins": x["wins"], "won_usd_est": round(x["usd"]),
            "main_sector": SECTORS.get(secs[0][0], "") if secs else "",
            "other_sectors": "; ".join(SECTORS.get(s, s) for s, _ in secs[1:3]),
            "epc": epc_class(x),
            "type": "goods supplier" if x["goods"] >= max(1, x["wins"] / 2) or x.get("ship_total") or (secs and secs[0][0] in GOODS_SECTORS and x.get("_sector_why") in ("own description", "company name or industry", "declared industry") and not x["works"])
                    else ("trader" if x.get("trader") else "works/services"),
            "logistics_role": logistics_role(f"{name} {x.get('industries', '')} {about} {items} {x.get('naics', '')}")
            if any(s_ in ("LOGISTICS", "PORTS") for s_, _ in secs[:1]) or "shipbuild" in name.lower() else "",
            "products": clean_products(about)[:300], "web_title": (wp.get("title") or "")[:120], "supplied": items[:240],
            "commodities": "; ".join(BY_ID[g]["name"] for g, _ in sorted(x["groups"].items(), key=lambda y: -y[1])[:3]
                                     if g in BY_ID),
            "main_cpv": max(x["cpv"].items(), key=lambda y: y[1])[0] if x["cpv"] else "",
            "buyer_countries": " ".join(sorted(c for c in x["buyer_c"] if c))[:80], "buyers": len(x["buyers"]),
            # cross-border evidence: won tenders abroad, verified by the research worker, or a known producer
            "exports": ("won abroad" if any(c and wc and c != wc for c in x["buyer_c"]) else
                        "verified (research)" if "Research" in x["sources"] else
                        "producer (Wikidata)" if "Wikidata products" in x["sources"] else
                        f"ships to the US ({x.get('ship12', 0)} shipments in 12 months)" if x.get("ship12") else
                        "shipped to the US (customs records)" if x.get("ship_total") else ""),
            "first_win": x["first"] if x["first"] != "9999" else "", "last_win": x["last"],
            "email": x["email"], "phone": x["phone"], "website": x["website"], "website_source": site_src, "address": x["address"],
            "legal_id": x["legal_id"], "sources": "; ".join(sorted(x["sources"])), "example_award": x["example"],
            "tier_reason": "", "origin": "B" if x.get("tier_b") else "A",  # new columns stay at the end (sheet formulas)
            "contact_level": ("email+phone" if x["email"] and x["phone"] else "email" if x["email"] else
                              "phone" if x["phone"] else "website only" if x["website"] else "address only" if x["address"] else "none"),
            "shipments_12m": x.get("ship12", "") if x.get("ship_total") else "", "hs_codes": x.get("hs", ""),
            "sector_why": x.get("_sector_why", ""), "sector_check": x.get("_sector_check", ""),
            # what kind of channel the e-mail is and whether its domain is the company's own (contact provenance)
            "email_kind": email_kind(x["email"], x["website"])[0], "email_domain": email_kind(x["email"], x["website"])[1],
            "contact_seen": today() if (x["email"] or x["phone"]) else "",  # last seen in a source, not a deliverability check
            "name_local": x.get("name_local", ""), "province": x.get("province", ""),
            # proven-supplier layer: the largest recent focus-sector award, and the role it suggests (new columns at the end)
            "proven": proven_text(x.get("pf_ev")), "proven_focus_usd": round(x["pf"]) if x.get("pf_ev") else "",
            "award_role": "", "award_role_basis": "", "dup_hint": "",
        })
        if x.get("pf_ev") or x["wins"]:
            out[-1]["award_role"], out[-1]["award_role_basis"] = award_role(
                name, x["works"], x["wins"], out[-1]["epc"], bool(x.get("trader")), x.get("_role_read", ""),
                (x.get("pf_ev") or {}).get("t", ""))
        rr = x.get("_role_read")  # the role its own website text reads as (open-source model, leads/describe.py): a reading, shown as such
        if rr == "trader":
            out[-1]["trader"] = "yes"
        elif rr and "manufacturer" not in out[-1]["type"]:
            out[-1]["type"] = (out[-1]["type"] + "; " if out[-1]["type"] else "") + ("manufacturer" if rr == "manufacturer" else "producer") + " (read from its website)"
    n_ref = apply_refined(out)
    try:  # e-mail domain deliverability (leads/mx_check.py, company-check cache restored read-only): mx_ok / no_mx / parked / disposable
        from .mx_check import load_results, verdict_for
        mxr = load_results()
    except Exception as e:  # noqa: BLE001
        log.warning("mx verdicts not loaded: %s", type(e).__name__); mxr = {}
    for r in out:
        r["email_mx"] = verdict_for(r.get("email"), mxr) if r.get("email") and mxr else ""
    try:  # GLEIF Golden Copy bulk match (leads/gleif_bulk.py, cache "gleif-" restored read-only): LEI, register id, parent
        from .gleif_bulk import load_matches
        gl = load_matches()
    except Exception as e:  # noqa: BLE001
        log.warning("gleif matches not loaded: %s", type(e).__name__); gl = {}
    n_gl = 0
    for r in out:
        m = gl.get(f"{r['supplier']}|{r['country']}")
        r["lei_ra_id"], r["lei_city"], r["lei_parent"] = "", "", ""
        if not m:
            continue
        n_gl += 1
        r["lei"] = r.get("lei") or m["lei"]
        r["legal_name"] = r.get("legal_name") or m["legal_name"][:150]
        r["lei_ra_id"] = f"{m.get('ra', '')}:{m.get('ra_entity_id', '')}".strip(":")
        r["lei_city"] = m.get("city", "")[:60]
        up = m.get("ultimate_parent_name") or m.get("parent_name")
        if up:
            r["lei_parent"] = f"{up[:100]} ({m.get('ultimate_parent_lei') or m.get('parent_lei')})"
    if gl:
        log.info("gleif bulk: %d suppliers carry a matched LEI", n_gl)
    for r in out:
        r["quality"] = quality(r)
        r["tier"], r["tier_reason"] = supplier_tier(r)
        r["_svc"] = service_only(r) or bool(GUARD_ID.search(r["supplier"]))
        if r["_svc"]:
            r["quality"] = round(r["quality"] * 0.6); r["type"] = "works/services"
        elif not r["main_sector"] or r.get("sector_why") == "name only (weak)":
            # nothing says what it sells (contracts known only by reference numbers): below the classified ones
            r["quality"] = round(r["quality"] * 0.7); r["_svc"] = True
    n_prom = promote_proven(out)
    log.info("proven by award: %s", n_prom)
    # best tier first; goods suppliers before on-site service firms; then quality
    out.sort(key=lambda r: (r["tier"], r["_svc"], -r["quality"], -r["won_usd_est"]))
    for r in out:
        r.pop("_svc", None)  # best tier first, then quality
    # Sanctions risk is shown, not filtered: the records stay (owner, 12 Nov 2026: an international company), each one
    # carries the risk so a person or an agent sees it before any contact. Comprehensive = country-wide sanctions
    # (UN/US/EU, and enemy-state rules for an Israeli owner); sectoral = sanctions on parts of the economy.
    for r in out:
        c = str(r.get("country") or "").upper()
        r["sanctions_risk"] = "comprehensive" if c in SANCTIONS_COMPREHENSIVE else "sectoral" if c in SANCTIONS_SECTORAL else ""
    out = balance_regions(out)
    out = [{"quality": r.pop("quality"), **r} for r in out]
    PRIVATE.mkdir(parents=True, exist_ok=True)
    try:
        if os.environ.get("UNIVERSE_NO_SHEET"):  # a measurement build (tenders.yml task=proven) writes no sheet tab
            raise RuntimeError("UNIVERSE_NO_SHEET set")
        classification_check(out)
    except Exception as e:  # noqa: BLE001
        log.warning("classification check tab: %s", e)
    cols = list(out[0].keys()) if out else ["supplier"]
    with open(PRIVATE / "universe.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    stats = {"awards": n_aw, "suppliers": len(out), "with_email": sum(1 for r in out if r["email"]),
             "with_phone": sum(1 for r in out if r["phone"]), "exporters": sum(1 for r in out if r["exports"]),
             "goods": sum(1 for r in out if r["type"] == "goods supplier"), "contacts_matched": n_ct, "customs_exporters": sum(1 for r in out if r["hs_codes"]), "customs_new": n_cu,
             "tier_A": sum(1 for r in out if r["origin"] == "A"), "tier_B_notable": n_b,
             **{f"tier_{t}_{n.lower()}": sum(1 for r in out if r["tier"] == t) for t, n in TIER_NAMES.items()},
             "with_website": sum(1 for r in out if r["website"]),
             "notable_total": sum(1 for r in out if r["notable"]),
             "notable_with_email": sum(1 for r in out if r["notable"] and r["email"]),
             "notable_with_phone": sum(1 for r in out if r["notable"] and r["phone"]),
             "notable_with_website": sum(1 for r in out if r["notable"] and r["website"]),
             "quality_40_plus": sum(1 for r in out if r["quality"] >= 40),
             "with_any_contact": sum(1 for r in out if r["email"] or r["phone"] or r["website"] or r["address"]),
             **{f"email_{v}": sum(1 for r in out if r.get("email_mx") == v) for v in ("mx_ok", "no_mx", "parked", "disposable")},
             "with_lei": sum(1 for r in out if r.get("lei")), "with_lei_parent": sum(1 for r in out if r.get("lei_parent"))}
    by_region = defaultdict(int)
    for r in out:
        by_region[r["region"] or "unknown"] += 1
    stats.update({f"region: {k}": v for k, v in sorted(by_region.items(), key=lambda y: -y[1])})
    log.info("universe %s", stats)
    (PRIVATE / "universe_stats.json").write_text(json.dumps(stats))
    # public aggregates (counts only, no names) for the ranking brain and the plays: proven suppliers per sector,
    # how many of them export, how many are Asian exporters (CHN, IND, TUR, VNM, KOR, MYS, THA, IDN), and per HS-4 heading
    ASIA = {"CHN", "IND", "TUR", "VNM", "KOR", "MYS", "THA", "IDN", "TWN", "PAK", "BGD"}
    by_sec, by_hs = defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0])
    for r in out:
        if str(r.get("tier")) not in ("1", "2"):
            continue
        b = by_sec[r.get("main_sector") or "Other"]
        b[0] += 1
        if r.get("exports"):
            b[1] += 1
            if r.get("country") in ASIA:
                b[2] += 1
        for h in str(r.get("hs_codes") or "").split():
            if h[:4].isdigit():
                by_hs[h[:4]][0] += 1
                if r.get("country") in ASIA:
                    by_hs[h[:4]][1] += 1
    with open(LEADS / "supplier_sectors.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["sector", "suppliers", "exporters", "asia_exporters"])
        for k, v in sorted(by_sec.items(), key=lambda y: -y[1][0]):
            w.writerow([k, *v])
    with open(LEADS / "supplier_hs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["hs4", "suppliers", "asia_suppliers"])
        for k, v in sorted(by_hs.items(), key=lambda y: -y[1][0]):
            w.writerow([k, *v])
    return out, stats


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    build()
