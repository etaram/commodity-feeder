"""Quality gate v1 for suppliers (owner, 13 Nov 2026: quality decides; only real information you can work with).

A supplier is REFINED only when every condition holds, each from evidence the system holds:
  identity   a company name and a valid ISO 3166 alpha-3 country (a legal id from a register or the site makes it 'strong')
  site       its own website was read and the name on the site matches the record (verdict ok, name match high)
  role       the site states what it is: manufacturer / producer, trader / distributor, contractor, service (a phrase found)
  products   at least two product or category phrases from the site that are not navigation or boilerplate
  contact    an official business contact published by the company: an email on the company's own domain, or a phone
  fresh      checked within FRESH_DAYS (the re-check rule)
Missing or failing conditions are counted per reason; nothing is filled by guessing. The gate never deletes a record.

  python -m leads.quality_gate <enrich dir>   counts only (public log); writes <dir>/refined.keys (private, root only)
"""
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

VERSION = "supplier-gate-1.2 (2026-11-13)"
FRESH_DAYS = 180
ISO3 = re.compile(r"^[A-Z]{3}$")
try:   # the ISO 3166-1 alpha-3 list the app uses (249 codes); a three-letter string alone is not a country
    _CN = Path(__file__).resolve().parents[1] / "dealdesk" / "lib" / "countrynames.json"
    ISO_CODES = set(json.loads(_CN.read_text(encoding="utf-8")))
except (OSError, ValueError):
    ISO_CODES = set()
EMAIL_RX = re.compile(r"^[a-z0-9._%+-]+@([a-z0-9-]+\.)+[a-z]{2,}$")
# second-level labels under which the registrable domain is three labels (acme.co.ke, acme.com.br); a host equal to
# such a suffix alone ('co.ke') is never a company's own domain
SLD = {"co", "com", "net", "org", "gov", "ac", "edu", "ltd", "plc", "or", "ne", "go", "gob", "nic", "mil", "info", "biz", "in", "sch"}
CTA = re.compile(r"^(get|learn|read|contact|discover|explore|view|see|find|latest|our|why|how|what|who|welcome|meet|join|"
                 r"subscribe|follow|download|request|book|call|email|send|click|shop now|buy now|sign|log|back|next|"
                 r"previous|home|news|updates?|testimonials?|reviews?|faq|careers?|blog|events?|gallery|portfolio)\b", re.I)
NEG = re.compile(r"\b(not|no|non|never|isn't|is not)\b", re.I)
NAV = re.compile(r"^(home|homepage|about|about us|who we are|contact|contact us|contacts|news|blog|careers?|jobs|privacy|"
                 r"cookie|cookies|terms|login|log in|sign in|register|search|menu|faq|sitemap|our company|company|team|"
                 r"our team|history|mission|vision|gallery|downloads?|media|events?|partners?|clients|references|"
                 r"welcome|follow us|social|newsletter|quick links|links|useful links|support|help|services|our services|"
                 r"products|our products|solutions|industries|projects|read more|learn more|more|top|language|english|"
                 r"inicio|contacto|nosotros|empresa|accueil|qui sommes-nous|startseite|kontakt|impressum|uber uns|über uns)$", re.I)
ROLE_OK = {"manufacturer", "producer", "trader", "distributor", "exporter", "contractor", "epc", "service", "supplier", "importer", "wholesaler"}
# v1.1: a role word in the company's own title, description or product phrases (site evidence, labelled 'site text').
# Each pattern names what the company says it is; a bare industry word is not enough.
SITE_ROLE = [
    ("manufacturer", re.compile(r"\b(manufactur\w*|fabricante|fabricant|fabrikant|hersteller|produttore|productor|produtor|"
                                r"producer|factory|mill|foundry|refinery|f[aá]brica|usine|werk)\b", re.I)),
    ("trader", re.compile(r"\b(distribut\w*|wholesal\w*|importer|importador|exporter|exportador|trading (company|house)|"
                          r"dealer|stockist|supplier of|suppliers of|proveedor|fornecedor|fournisseur|lieferant|grossiste|"
                          r"großhandel|comercializadora)\b", re.I)),
    ("contractor", re.compile(r"\b(contractor|contracting|construction company|constructora|construtora|bauunternehmen|"
                              r"entreprise de (construction|travaux)|civil works|engineering and construction|epc)\b", re.I)),
    ("service", re.compile(r"\b(consult\w*|services? (company|provider)|engineering services|maintenance|facility management|"
                           r"logistics|freight|laborator(y|ies)|software|it solutions)\b", re.I)),
]


def product_phrases(rec):
    out = []
    for p in rec.get("products") or []:
        t = re.sub(r"\s+", " ", str(p)).strip(" -|:·•")
        if len(t) < 3 or len(t) > 80 or NAV.match(t) or re.fullmatch(r"[\W\d_]+", t):
            continue
        if re.search(r"(©|copyright|all rights|cookie|privacy|javascript|\bcall us\b|\bemail us\b)", t, re.I):
            continue
        if CTA.match(t):        # calls to action and page furniture ('Get in touch', 'Latest updates') are not products
            continue
        out.append(t)
    return list(dict.fromkeys(out))


def registrable(host):
    parts = [x for x in (host or "").lower().strip(".").removeprefix("www.").split(".") if x]
    if len(parts) < 2:
        return ""
    if len(parts) >= 3 and parts[-2] in SLD and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    if len(parts) == 2 and parts[0] in SLD and len(parts[1]) == 2:
        return ""                     # 'co.ke' alone is a public suffix, not a company domain
    return ".".join(parts[-2:])


def valid_phone(p):
    digits = re.sub(r"\D", "", str(p or ""))
    return 7 <= len(digits) <= 15 and not re.search(r"[A-Za-z]{3,}", str(p))


def official_contact(rec):
    site = registrable(rec.get("domain") or "")
    for e in rec.get("emails") or []:
        addr = (e.get("email") if isinstance(e, dict) else str(e)).strip().lower()
        if not EMAIL_RX.match(addr):
            continue
        host = registrable(addr.split("@")[-1])
        if site and host and host == site:
            return "email on own domain"
    if any(valid_phone(p) for p in rec.get("phones") or []):
        return "phone on own site"
    return ""


# v1.2: site text counts only where the company describes ITSELF (subject wording), never customers or markets
SELF_ROLE = [
    ("manufacturer", re.compile(r"\b(we (manufacture|produce|fabricate)|(leading |a |an |the )?(manufacturer|producer|maker) of|"
                                r"(is|are) (a |an |the )?(leading )?(manufacturer|producer)|our (factory|plant|mill|production)|"
                                r"fabricante de|fabricant de|hersteller (von|für)|produttore di|productor de|produtor de)\b", re.I)),
    ("trader", re.compile(r"\b(we (distribute|import|export|supply|trade)|(leading |a |an |the |official |authori[sz]ed )?"
                          r"(distributor|importer|exporter|wholesaler|stockist|dealer|supplier) (of|for)|(is|are) (a |an |the )?"
                          r"(leading )?(distributor|importer|exporter|wholesaler|trading company)|trading company|"
                          r"distribuidor de|importador de|exportador de|proveedor de|fornecedor de|fournisseur de)\b", re.I)),
    ("contractor", re.compile(r"\b((is|are) (a |an |the )?(leading )?(contractor|construction company|epc contractor)|"
                              r"(general|main|civil|electrical|mechanical|epc) contractor|construction company|"
                              r"engineering,? procurement and construction|constructora|construtora)\b", re.I)),
    ("service", re.compile(r"\b(we (provide|offer|deliver) [a-z ]{0,30}services|(is|are) (a |an |the )?(leading )?[a-z ]{0,20}"
                           r"(consultancy|consulting firm|service provider|services company|logistics company|laboratory))\b", re.I)),
]
CUSTOMER_CTX = re.compile(r"\b(for|to|serving|serve|help(s|ing)?|with)\s+(\w+\s+){0,3}(manufacturers|producers|factories|distributors|contractors)\b", re.I)


def roles_of(rec):
    """(roles, basis). A role field or role phrase from the site analysis counts unless negated; site text counts only
    when the company describes itself (v1.2), not its customers."""
    r = set()
    for x in (rec.get("roles") or []) + ([{"role": rec["role"]}] if rec.get("role") else []):
        v = (x.get("role") if isinstance(x, dict) else str(x)).lower()
        phrase = (x.get("phrase") if isinstance(x, dict) else "") or ""
        if NEG.search(v) or NEG.search(phrase[:20]):
            continue
        r |= {k for k in ROLE_OK if re.search(rf"\b{k}", v)}
    if r:
        return sorted(r), "site role phrase"
    text = " ".join([str(rec.get("title") or ""), str(rec.get("description") or "")])
    text_wo_customers = CUSTOMER_CTX.sub(" ", text)
    r |= {role for role, rx in SELF_ROLE if rx.search(text_wo_customers)}
    return sorted(r), ("site text (self-description)" if r else "")


def gate(rec, today=None):
    """(refined: bool, failed: [reasons], facts: dict)"""
    today = today or dt.date.today()
    fails = []
    country = str(rec.get("country") or "").upper()
    if not (rec.get("supplier") and ISO3.match(country) and (not ISO_CODES or country in ISO_CODES)):
        fails.append("identity: no name or no valid ISO 3166 country")
    if rec.get("verdict") != "ok":
        fails.append(f"site: {rec.get('verdict') or 'not read'}")
    elif rec.get("name_match") != "high":
        fails.append(f"site: name match {rec.get('name_match') or 'unknown'}")
    roles, basis = roles_of(rec)
    if not roles:
        fails.append("role: not stated on the site")
    prods = product_phrases(rec)
    if len(prods) < 2:
        fails.append("products: fewer than 2 product phrases")
    contact = official_contact(rec)
    if not contact:
        fails.append("contact: no email on own domain and no phone")
    try:
        checked = dt.date.fromisoformat(str(rec.get("checked") or rec.get("checked_at") or "")[:10])
        if checked > today:
            fails.append("fresh: check date in the future")
        elif (today - checked).days > FRESH_DAYS:
            fails.append("fresh: checked more than 180 days ago")
    except ValueError:
        fails.append("fresh: no check date")
    # strong identity: an identifier with a scheme and at least 5 digits/characters (VAT, LEI, CNPJ, company number...)
    strong = any(isinstance(x, dict) and x.get("kind") and len(re.sub(r"\W", "", str(x.get("value") or ""))) >= 5
                 for x in rec.get("legal_ids") or [])
    return not fails, fails, {"roles": roles, "role_basis": basis, "products": len(prods), "contact": contact, "strong_identity": strong, "country": country}


def run(d):
    d = Path(d)
    n, ok, strong = 0, 0, 0
    first, every = Counter(), Counter()
    by_country, by_role, by_basis = Counter(), Counter(), Counter()
    keys = []
    latest = {}      # the newest record of a key wins (a discovered website is appended later than the first read)
    with open(d / "site.jsonl", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                every["unreadable line"] += 1
                continue
            k = rec.get("key")
            if k:
                latest[k] = gate(rec) + (rec.get("website_basis", ""),)
    discovered_refined = 0
    for k, (passed, fails, facts, wb) in latest.items():
        n += 1
        for x in fails:
            every[x.split(":")[0]] += 1
        if fails:
            first[fails[0].split(":")[0] + ": " + fails[0].split(": ", 1)[-1][:40]] += 1
            continue
        ok += 1; strong += facts["strong_identity"]; by_basis[facts["role_basis"]] += 1
        discovered_refined += bool(wb)
        by_country[facts["country"]] += 1
        for r in facts["roles"]:
            by_role[r] += 1
        keys.append(k)
    (d / "refined.keys").write_text("\n".join(keys), encoding="utf-8")
    out = {"gate": VERSION, "suppliers_checked": n, "refined": ok, "refined_with_legal_id": strong, "refined_via_discovered_site": discovered_refined,
           "refined_countries": len(by_country), "refined_by_role": dict(by_role.most_common()), "refined_by_role_basis": dict(by_basis),
           "refined_top_countries": dict(by_country.most_common(25)),
           "failing_condition_counts": dict(every.most_common()), "first_failure": dict(first.most_common(25))}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "/opt/sinder/enrich")
