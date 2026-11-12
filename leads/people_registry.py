"""Key people at supplier companies from official company registers (the 'registry' lane of leads/enrich_server.py).

Business role information only: a person's name, the role the register records, since when (when the register says),
the register record as the source, and the date it was read. Birth dates (some registers publish the year and month),
addresses, personal ID numbers (CPF), nationality and shareholdings are never kept: each parser copies only the
whitelisted fields. Nothing is fetched from linkedin.com: each person gets a LinkedIn people-search link (name and
company) that the owner opens in his own browser.

Registers (verified on 12 Nov 2026 from the company server; free, official data, no login, no CAPTCHA):
  FRA  API Recherche d'entreprises (recherche-entreprises.api.gouv.fr, DINUM, open, keyless, 7 requests/s; we use 2/s):
       dirigeants of the RNE. Id: SIREN (from a FR VAT number or a SIREN/SIRET/RCS printed on the site), else name.
  NOR  Bronnoysund Register Centre, Enhetsregisteret (data.brreg.no, NLOD licence, keyless): roles (daglig leder,
       styre, innehaver). Id: organisasjonsnummer (NO VAT / Org.nr), else name.
  CZE  ARES (ares.gov.cz, Ministry of Finance, keyless): public register record (statutory body, partners). Id: ICO
       (CZ VAT of a legal entity / IC printed), else name.
  BRA  Receita Federal CNPJ open data (QSA: partners and administrators) through BrasilAPI (brasilapi.com.br, open
       source, keyless; minhareceita.org as the fallback mirror of the same open data). Id: CNPJ printed on the site only.
  GBR  Companies House public data API (free; needs an API key): officers. OFF until COMPANIES_HOUSE_API_KEY is set.
       Id: company number printed on the site, else name.
Checked and not used: Poland KRS open API (api-krs.ms.gov.pl answers, but masks the names of board members, e.g.
"J*** K*****"; the VAT white list returns no representatives for companies), Finland PRH open data (no persons), Denmark CVR (system-to-system access needs credentials from
the Danish Business Authority), Slovakia RPO and Estonia (possible next: small share of the supplier list).

Identity rule: a registration id the company's own site prints (and the site names the company), or else exactly
one ACTIVE register entity whose name equals the supplier's name after legal suffixes (leads/registry_check.norm), in the
same country. Two or more exact matches: 'ambiguous', nothing kept. Names shorter than 4 characters: not searched.
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import quote

UA = "Mozilla/5.0 (compatible; SinderCompanyCheck/1.0; +https://github.com/etaram/commodity-feeder)"
COUNTRIES = {"FRA": "fr", "NOR": "no", "CZE": "cz", "BRA": "br", "GBR": "gb"}
SOURCE_NAME = {"fr": "Registre national des entreprises (API Recherche d'entreprises)", "no": "Bronnoysund Enhetsregisteret",
               "cz": "ARES / Czech public register", "br": "Receita Federal CNPJ (QSA)",
               "gb": "Companies House"}
RATE = {"fr": 2.0, "no": 2.0, "cz": 1.0, "br": 0.5, "gb": 1.5}  # requests per second, under each source's limit
MAX_PEOPLE = 10


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# ---------------------------------------------------------------- names and roles (pure)
PARTICLES = {"de", "da", "das", "do", "dos", "du", "des", "del", "della", "di", "van", "von", "der", "den", "la", "le", "e", "y", "af", "zu"}


def person_case(s):
    """'JEAN-PIERRE DE LA FONTAINE' -> 'Jean-Pierre de la Fontaine'; 'Jan NOVÁK' -> 'Jan Novák'; mixed-case words are kept."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    out = []
    for i, w in enumerate(s.split(" ") if s else []):
        if w.isupper() or (w.islower() and not (i and w in PARTICLES)):
            lw = w.lower()
            w = lw if (i and lw in PARTICLES) else "-".join(p[:1].upper() + p[1:] for p in lw.split("-"))
        out.append(w)
    return " ".join(out)


def title_case(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return (s[:1].upper() + s[1:].lower()) if s.isupper() else s


# role buckets the panel and the refined layer use; registers' own titles are kept as the title
ROLE_RULES = [
    ("skip", r"commissaire aux comptes|auditor|revisor|\bREVI\b|regnskapsf|kontaktperson|\bVARA\b|varamedlem|suppl[ée]ant|"
             r"prokurent|prokurist|likvid|rada nadzorcza|nadzorcz|dozor[cč]í|conseil de surveillance|supervisory|secretary|"
             r"representante legal|\bREPR\b|norsk representant|kontrollkomit"),
    ("chief executive", r"pr[ée]sident(?! du conseil de surveillance)|directeur g[ée]n[ée]ral(?! d[ée]l[ée]gu)|\bg[ée]rant|daglig leder|adm\.? ?direkt|"
                        r"\bDAGL\b|(?<!wice)prezes zarz|jednatel|p[řr]edseda p[řr]edstavenstva|diretor[a]? presidente|presidente|administrador|"
                        r"managing director|chief executive|general manager"),
    ("founder / owner", r"innehaver|\bINNH\b|deltaker|\bDTPR\b|\bDTSO\b|komplement|wsp[óo]lnik|s[óo]cio|spole[čc]n[ií]k|"
                        r"associ[ée]|titular|owner|member of llp|llp.*member|propri[ée]taire|exploitant"),
    ("director / board", r"administrateur|membre du directoire|directeur g[ée]n[ée]ral d[ée]l[ée]gu[ée]|styrets leder|nestleder|"
                         r"styremedlem|\bLEDE\b|\bNEST\b|\bMEDL\b|\bSTYR\b|wiceprezes|cz[łl]onek zarz|cz[łl]onek|člen|clen|"
                         r"místop[řr]edseda|p[řr]edseda|statut[áa]rn|diretor|conselheiro|director|board"),
]
ROLE_RX = [(k, re.compile(rx, re.I)) for k, rx in ROLE_RULES]
ROLE_ORDER = {"chief executive": 0, "founder / owner": 1, "director / board": 2}


def role_of(title):
    for k, rx in ROLE_RX:
        if rx.search(title or ""):
            return "" if k == "skip" else k
    return ""


def linkedin_search_url(name, company):
    """A LinkedIn people search for this person at this company: the owner opens it in his own browser (nothing is fetched)."""
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote(f"{name} {company}"[:120])


def short_company(name):
    from .registry_check import LEGAL, LEGAL_LONG
    n = re.sub(r"\s+", " ", LEGAL.sub(" ", LEGAL_LONG.sub(" ", str(name or "")))).strip(" ,.-")
    return n or str(name or "")


def person(name, title, source, url, company, since=""):
    """The only shape a register person is stored in (business role information only)."""
    name, title = person_case(name), title_case(title)
    role = role_of(title)
    if not name or not role or len(name) > 60 or len(name.split()) < 2:
        return None
    p = {"name": name, "title": title[:80], "role": role, "source": url, "source_name": SOURCE_NAME[source], "basis": "official company register",
         "confidence": "official registry", "checked": now()[:10], "linkedin_search": linkedin_search_url(name, short_company(company))}
    if since and re.match(r"^\d{4}-\d{2}-\d{2}$", str(since)):
        p["since"] = since
    return p


def fold(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().replace("-", " ").strip()


def finish(people):
    seen, out = set(), []
    for p in sorted([p for p in people if p], key=lambda p: ROLE_ORDER.get(p["role"], 9)):
        k = fold(p["name"])
        if k not in seen:
            seen.add(k); out.append(p)
    return out[:MAX_PEOPLE]


# ---------------------------------------------------------------- ids from the company's own site (pure)
def site_ids(country, legal_ids):
    """legal_ids of a website check ([{kind, value}]) -> the register id for this country's register, or ''."""
    for x in legal_ids or []:
        k, v = str(x.get("kind", "")), re.sub(r"[\s.\-/]", "", str(x.get("value", ""))).upper()
        if country == "FRA":
            if k == "VAT" and re.fullmatch(r"FR[0-9A-Z]{2}\d{9}", v):
                return v[4:]
            if k in ("SIREN", "SIRET", "RCS") and re.fullmatch(r"\d{9}(\d{5})?", v):
                return v[:9]
        elif country == "NOR":
            m = re.fullmatch(r"(?:NO)?(\d{9})(?:MVA)?", v)
            if m and k in ("VAT", "Org.nr"):
                return m.group(1)
        elif country == "CZE":
            if (k == "VAT" and re.fullmatch(r"CZ\d{8}", v)) or (k == "ICO" and re.fullmatch(r"\d{8}", v)):
                return v[-8:]
        elif country == "BRA":
            if k == "CNPJ" and re.fullmatch(r"\d{14}", v):
                return v
        elif country == "GBR":
            if k == "Company no." and re.fullmatch(r"(?:[A-Z]{2}\d{6}|\d{6,8})", v):
                return v.zfill(8)
    return ""


def same_name(a, b):
    from .registry_check import norm
    na, nb = norm(a), norm(b)
    return bool(na) and len(na) >= 4 and na == nb


def pick(name, cands):
    """[(id, register name, active)] -> (id, 'exact name') | (None, 'ambiguous' | 'no match')."""
    exact = list(dict.fromkeys(i for i, n, act in cands if act and same_name(name, n)))
    if len(exact) == 1:
        return exact[0], "exact name"
    return None, "ambiguous" if exact else "no match"


# ---------------------------------------------------------------- parsers (pure: register JSON -> entity, people)
def parse_fr(res, company):
    """One result of recherche-entreprises /search -> (entity, people)."""
    siren = res.get("siren", "")
    url = f"https://annuaire-entreprises.data.gouv.fr/dirigeants/{siren}"
    ent = {"id": siren, "name": res.get("nom_raison_sociale") or res.get("nom_complet") or "", "active": res.get("etat_administratif") == "A", "url": url}
    ppl = []
    for d in res.get("dirigeants") or []:
        if d.get("type_dirigeant") != "personne physique":
            continue
        first = (re.split(r"[\s,]+", str(d.get("prenoms") or "").strip()) or [""])[0]
        nom = re.sub(r"\s*\(.*?\)", "", str(d.get("nom") or ""))  # "(usage name)" left out
        ppl.append(person(f"{first} {nom}", d.get("qualite") or "", "fr", url, company))
    return ent, finish(ppl)


def fr_candidates(js):
    return [(r.get("siren"), r.get("nom_raison_sociale") or re.sub(r"\s*\(.*\)$", "", r.get("nom_complet") or ""), r.get("etat_administratif") == "A")
            for r in (js or {}).get("results") or []]


def parse_no(unit, roles, company):
    org = unit.get("organisasjonsnummer", "")
    url = f"https://virksomhet.brreg.no/nb/oppslag/enheter/{org}"
    ent = {"id": org, "name": unit.get("navn", ""), "url": url, "website": unit.get("hjemmeside") or "",
           "active": not (unit.get("konkurs") or unit.get("underAvvikling") or unit.get("underTvangsavviklingEllerTvangsopplosning") or unit.get("slettedato"))}
    ppl = []
    for g in (roles or {}).get("rollegrupper") or []:
        for r in g.get("roller") or []:
            pr = r.get("person")
            if not pr or r.get("fratraadt") or r.get("avregistrert") or pr.get("erDoed"):
                continue
            n = pr.get("navn") or {}
            nm = " ".join(x for x in (n.get("fornavn"), n.get("mellomnavn"), n.get("etternavn")) if x)
            t = (r.get("type") or {})
            ppl.append(person(nm, f"{t.get('beskrivelse', '')} ({t.get('kode', '')})", "no", url, company))
    return ent, finish(ppl)


def no_candidates(js):
    return [(u.get("organisasjonsnummer"), u.get("navn", ""), not (u.get("konkurs") or u.get("underAvvikling") or u.get("slettedato")))
            for u in ((js or {}).get("_embedded") or {}).get("enheter") or []]


def parse_cz(js, company):
    ico = js.get("icoId") or ""
    zs = js.get("zaznamy") or []
    z = next((x for x in zs if x.get("primarniZaznam")), zs[0] if zs else {})
    url = f"https://ares.gov.cz/ekonomicke-subjekty?ico={ico}"
    names = [x for x in z.get("obchodniJmeno") or [] if not x.get("datumVymazu")]
    ent = {"id": ico, "name": (names[-1] if names else {}).get("hodnota", ""), "url": url, "active": (z.get("stavSubjektu") or "") == "AKTIVNI"}
    ppl = []
    for org in z.get("statutarniOrgany") or []:
        if org.get("datumVymazu"):
            continue
        for m in org.get("clenoveOrganu") or []:
            fo = m.get("fyzickaOsoba")
            fn = ((m.get("clenstvi") or {}).get("funkce") or {})
            if not fo or m.get("datumVymazu") or fn.get("zanikFunkce"):
                continue
            title = fn.get("nazev") or m.get("nazevAngazma") or org.get("nazevOrganu") or ""
            ppl.append(person(f"{fo.get('jmeno', '')} {fo.get('prijmeni', '')}", title, "cz", url, company, fn.get("vznikFunkce") or ""))
    for grp in z.get("spolecnici") or []:
        if grp.get("datumVymazu"):
            continue
        for sp in grp.get("spolecnik") or []:
            o = sp.get("osoba") or {}
            fo = o.get("fyzickaOsoba")
            if not fo or o.get("datumVymazu") or sp.get("datumVymazu"):
                continue
            ppl.append(person(f"{fo.get('jmeno', '')} {fo.get('prijmeni', '')}", o.get("nazevAngazma") or "Společník", "cz", url, company))
    return ent, finish(ppl)


def cz_candidates(js):
    out = []
    for e in (js or {}).get("ekonomickeSubjekty") or []:
        reg = e.get("seznamRegistraci") or {}
        out.append((e.get("ico"), e.get("obchodniJmeno", ""), reg.get("stavZdrojeVr") == "AKTIVNI"))
    return out


BR_ROLES = {"5": "Administrador", "10": "Diretor", "16": "Presidente", "22": "Sócio", "49": "Sócio-Administrador", "65": "Titular"}


def parse_br(js, company):
    cnpj = str(js.get("cnpj", ""))
    url = f"https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpjreva_Solicitacao.asp?cnpj={cnpj}"
    ent = {"id": cnpj, "name": js.get("razao_social", ""), "url": url, "active": str(js.get("situacao_cadastral")) in ("2", "ATIVA")}
    ppl = []
    for s in js.get("qsa") or []:
        if str(s.get("identificador_de_socio")) not in ("2", "3"):  # 1 is a company partner
            continue
        title = s.get("qualificacao_socio") or BR_ROLES.get(str(s.get("codigo_qualificacao_socio")), "")
        ppl.append(person(s.get("nome_socio", ""), title, "br", url, company, s.get("data_entrada_sociedade") or ""))
    return ent, finish(ppl)


def parse_gb(profile, officers, company):
    num = profile.get("company_number", "")
    url = f"https://find-and-update.company-information.service.gov.uk/company/{num}/officers"
    ent = {"id": num, "name": profile.get("company_name", ""), "url": url, "active": profile.get("company_status") == "active"}
    ppl = []
    for o in (officers or {}).get("items") or []:
        if o.get("resigned_on") or o.get("officer_role", "").startswith("corporate"):
            continue
        n = str(o.get("name", ""))
        if "," in n:  # "SURNAME, Forename Middle"
            sur, given = n.split(",", 1)
            n = f"{given.strip()} {person_case(sur.strip())}"
        ppl.append(person(n, o.get("officer_role", "").replace("-", " "), "gb", url, company, o.get("appointed_on") or ""))
    return ent, finish(ppl)


def gb_candidates(js):
    return [(i.get("company_number"), i.get("title", ""), i.get("company_status") == "active") for i in (js or {}).get("items") or []]


# ---------------------------------------------------------------- network (server job)
class Blocked(Exception):
    pass


def _check(r):
    if r.status_code in (403, 429) or r.status_code >= 500:
        raise Blocked(f"HTTP {r.status_code}")
    return r


def _get(s, url, rate, **kw):
    rate.wait()
    return _check(s.get(url, timeout=25, **kw))


def available(src):
    return src != "gb" or bool(os.environ.get("COMPANIES_HOUSE_API_KEY"))


def lookup(s, src, it, site, rate):
    """One supplier in one register -> lane record {key, checked_at, source, match, entity?, people}."""
    name, company = it["name"], it["name"]
    site = site or {}
    site_ok = site.get("verdict") == "ok" and site.get("name_match") in ("high", "partial")
    rid = site_ids(it["country"], site.get("legal_ids")) if site_ok else ""
    base = {"key": it["key"], "checked_at": now(), "source": src}
    match = "registration id on the company's own site" if rid else ""
    from .registry_check import norm
    if not rid and len(norm(name)) < 4:
        return {**base, "match": "skipped", "why": "name too short to match"}
    if src == "fr":
        url = "https://recherche-entreprises.api.gouv.fr/search"
        if rid:
            js = _get(s, url, rate, params={"q": rid, "per_page": 3}).json()
            res = next((r for r in js.get("results") or [] if r.get("siren") == rid), None)
        else:
            js = _get(s, url, rate, params={"q": name[:120], "per_page": 25}).json()
            rid, match = pick(name, fr_candidates(js))
            res = next((r for r in js.get("results") or [] if r.get("siren") == rid), None) if rid else None
        if not res:
            return {**base, "match": match if not rid else "id not found"}
        ent, ppl = parse_fr(res, company)
    elif src == "no":
        if not rid:
            js = _get(s, "https://data.brreg.no/enhetsregisteret/api/enheter", rate, params={"navn": name[:120], "size": 25}).json()
            rid, match = pick(name, no_candidates(js))
            if not rid:
                return {**base, "match": match}
        r = _get(s, f"https://data.brreg.no/enhetsregisteret/api/enheter/{rid}", rate)
        if r.status_code != 200:
            return {**base, "match": "id not found"}
        roles = _get(s, f"https://data.brreg.no/enhetsregisteret/api/enheter/{rid}/roller", rate)
        ent, ppl = parse_no(r.json(), roles.json() if roles.status_code == 200 else {}, company)
    elif src == "cz":
        if not rid:
            rate.wait()
            r = _check(s.post("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat",
                              json={"obchodniJmeno": name[:120], "pocet": 25}, timeout=25))
            rid, match = pick(name, cz_candidates(r.json() if r.status_code == 200 else {}))
            if not rid:
                return {**base, "match": match}
        r = _get(s, f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/{rid}", rate)
        if r.status_code != 200:
            return {**base, "match": "no public register record"}
        ent, ppl = parse_cz(r.json(), company)
    elif src == "br":
        if not rid:
            return {**base, "match": "skipped", "why": "no CNPJ on the company's own site"}
        js = None
        for u in (f"https://brasilapi.com.br/api/cnpj/v1/{rid}", f"https://minhareceita.org/{rid}"):
            try:
                r = _get(s, u, rate)
            except Blocked:
                continue
            if r.status_code == 200:
                js = r.json(); break
        if js is None:
            return {**base, "match": "id not found"}
        ent, ppl = parse_br(js, company)
    elif src == "gb":
        key = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
        if not key:
            return None
        auth = (key, "")
        if not rid:
            js = _get(s, "https://api.company-information.service.gov.uk/search/companies", rate, params={"q": name[:120], "items_per_page": 20}, auth=auth).json()
            rid, match = pick(name, gb_candidates(js))
            if not rid:
                return {**base, "match": match}
        r = _get(s, f"https://api.company-information.service.gov.uk/company/{rid}", rate, auth=auth)
        if r.status_code != 200:
            return {**base, "match": "id not found"}
        o = _get(s, f"https://api.company-information.service.gov.uk/company/{rid}/officers", rate, params={"items_per_page": 50}, auth=auth)
        ent, ppl = parse_gb(r.json(), o.json() if o.status_code == 200 else {}, company)
    else:
        return None
    if not ent.get("active"):
        return {**base, "match": "register entity not active", "entity": ent, "people": []}
    if match.startswith("registration id"):
        ent["name_check"] = "same name" if same_name(name, ent["name"]) else "different name on the register"
    if ent.get("website") and site.get("domain"):
        from .company_profile import _dom
        ent["website_matches"] = _dom(ent["website"]) == site["domain"]
    return {**base, "match": match, "entity": ent, "people": ppl}


# ---------------------------------------------------------------- probe (the register answers, sealed by the shell)
PROBES = [
    ("FR id", "https://recherche-entreprises.api.gouv.fr/search?q=542051180&per_page=2"),
    ("NO roles", "https://data.brreg.no/enhetsregisteret/api/enheter/923609016/roller"),
    ("CZ vr", "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/03479919"),
    ("BR cnpj", "https://brasilapi.com.br/api/cnpj/v1/33000167000101"),
    ("GB without key", "https://api.company-information.service.gov.uk/company/00102498/officers"),
]


def probe(out):
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    res = {}
    for lab, u in PROBES:
        try:
            r = s.get(u, timeout=25)
            res[lab] = {"status": r.status_code, "body": r.text[:120000]}
            print(lab, r.status_code, len(r.text))
        except Exception as e:  # noqa: BLE001
            res[lab] = {"error": type(e).__name__}
            print(lab, "error", type(e).__name__)
        time.sleep(1)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)


if __name__ == "__main__":
    if sys.argv[1] == "probe":
        probe(sys.argv[2])
