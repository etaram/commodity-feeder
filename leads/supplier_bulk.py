"""Bulk supplier registers: official open lists of manufacturers and producers, downloaded whole and sealed into the
supplier universe through the same encrypted drop route as leads/importer.py (data/import/bulk-<source>.enc).
leads/universe.py merges them on its next build (same normalised name and country, or the same website, merge into one
record; nothing is overwritten, only empty fields are filled), and the refinement (company-check website check, describe
role and products, registry check) then decides what is refined. Nothing here is marked verified.

Sources (each: official, open, automated download allowed, no login, robots.txt read before the first request):

  traces  EU TRACES NT establishment lists (European Commission, DG SANTE): non-EU establishments approved to export food
          of animal origin to the EU, per country and section (meat, poultry, fishery products, dairy, eggs, casings ...).
          Public lists, no login: webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication.
          Reuse: Commission documents and data are reusable under Decision 2011/833/EU (attribution, no distortion).
          Every listed establishment is a food business operator approved by its competent authority (manufacturer,
          processing plant, cold store, vessel); the approval number is kept as evidence, and EU approval is the
          export evidence.
  denue   Mexico INEGI DENUE (Directorio Estadistico Nacional de Unidades Economicas), national bulk CSV, manufacturing
          (SCIAN 31-33), establishments with 51 or more persons employed (per_ocu bands 51-100, 101-250, 251+).
          Licence: INEGI "Terminos de libre uso de la informacion del INEGI" (free use, including commercial, with
          attribution to INEGI). Establishments are grouped by legal name (razon social) into one company record; a row
          whose legal name carries no company form (S.A., S. de R.L., S.C., cooperative ...) may be a natural person and
          is skipped.
  prh     Finland PRH / YTJ open data (avoindata.prh.fi, opendata-ytj-api v3 all_companies bulk file), CC BY 4.0
          (Finnish Patent and Registration Office). Active companies whose main line of business is manufacturing
          (TOL 2008 divisions 10-33). Sole traders (toiminimi, private traders: natural persons) are skipped.
  fsis    USDA FSIS Meat, Poultry and Egg Product Inspection Directory (public domain, US Government work). The site
          answers 403 to automated clients from the runner (bot protection on fsis.usda.gov, robots.txt included); it is
          not worked around. The source is kept here so it runs once the file is reachable.

Rows (importer format): supplier, name_local, country (ISO3), province, city, industry, products, website, email, phone,
address, source, source_url, notable (False), basis, employees, plus evidence keys: role ("manufacturer" / "producer"),
legal_id, approval_no, size_band, export_evidence, activities.

Public output: data/leads/supplier_bulk_status.json (counts only). The sealed drop is rewritten only when its content
changed (content hash kept in the status).

  python -m leads.supplier_bulk run all|traces,denue,prh [--limit N]
"""
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.robotparser
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

import requests

from .common import DATA, LEADS, log

UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
STATUS = LEADS / "supplier_bulk_status.json"
IMPORT_DIR = DATA / "import"
_S = None


def session():
    global _S
    if _S is None:
        _S = requests.Session()
        _S.headers.update({"User-Agent": UA, "Accept-Language": "en"})
    return _S


_ROBOTS = {}


def allowed(url):
    """robots.txt of the host (a missing robots.txt allows everything; an unreadable one, 401/403, refuses)."""
    from urllib.parse import urlsplit
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = session().get(base + "/robots.txt", timeout=30)
            if r.status_code in (401, 403):
                rp.disallow_all = True
            elif r.status_code >= 400 or "text/html" in r.headers.get("content-type", ""):
                rp.allow_all = True
            else:
                rp.parse(r.text.splitlines())
        except requests.RequestException:
            rp.allow_all = True
        _ROBOTS[base] = rp
    return _ROBOTS[base].can_fetch(UA, url)


def fetch(url, pause=1.0, **kw):
    if not allowed(url):
        raise PermissionError(f"robots.txt disallows {url}")
    for i in range(4):
        try:
            r = session().get(url, timeout=kw.pop("timeout", 120), **kw)
        except requests.RequestException as e:
            log.warning("BULK %s: %s (try %d)", url[:120], type(e).__name__, i + 1); time.sleep(5 * (i + 1)); continue
        if r.status_code in (429, 502, 503, 504):
            time.sleep(10 * (i + 1)); continue
        time.sleep(pause)
        return r
    raise RuntimeError(f"no answer from {url}")


def download(url, dest):
    """Stream a large file to disk (robots.txt checked)."""
    if not allowed(url):
        raise PermissionError(f"robots.txt disallows {url}")
    with session().get(url, timeout=600, stream=True) as r:
        r.raise_for_status()
        n = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk); n += len(chunk)
    log.info("BULK downloaded %s: %.1f MB", url.rsplit("/", 1)[-1], n / 1e6)
    return dest


def fold(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def title_case(s):
    """MOSTLY UPPER-CASE register names to a readable form, keeping legal-form abbreviations upper case."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if not s or sum(c.isupper() for c in s) < 0.7 * max(1, sum(c.isalpha() for c in s)):
        return s
    keep = {"SA", "CV", "DE", "RL", "SAPI", "SAB", "SC", "AC", "SPR", "RI", "S.A.", "C.V.", "R.L.", "S.C.", "A.C.", "S.P.R.", "R.I.", "SRL", "MI", "SAS"}
    out = []
    for w in s.split(" "):
        out.append(w if w.strip(",.") in keep or len(w) <= 2 and w.isupper() and w.strip(".,") in keep else w.capitalize())
    return " ".join(out)


# ------------------------------------------------------------------------------------------------ Mexico INEGI DENUE
DENUE_URL = "https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_31-33_csv.zip"
DENUE_BANDS = {"51 a 100 personas": "51-100", "101 a 250 personas": "101-250", "251 y más personas": "251+",
               "251 y mas personas": "251+"}
SCIAN3 = {"311": "Food manufacturing", "312": "Beverage and tobacco product manufacturing", "313": "Textile mills",
          "314": "Textile product mills", "315": "Apparel manufacturing", "316": "Leather and allied product manufacturing",
          "321": "Wood product manufacturing", "322": "Paper manufacturing", "323": "Printing and related support activities",
          "324": "Petroleum and coal products manufacturing", "325": "Chemical manufacturing", "326": "Plastics and rubber products manufacturing",
          "327": "Nonmetallic mineral product manufacturing (cement, glass, ceramics)", "331": "Primary metal manufacturing (steel, aluminium, copper)",
          "332": "Fabricated metal product manufacturing", "333": "Machinery manufacturing",
          "334": "Computer and electronic product manufacturing", "335": "Electrical equipment, appliance and component manufacturing",
          "336": "Transportation equipment manufacturing (vehicles, parts)", "337": "Furniture and related product manufacturing",
          "339": "Miscellaneous manufacturing (medical equipment and supplies, other)"}
MX_FORM = re.compile(r"\b(S\.?\s?A\.?|S\.?\s?A\.?\s?P\.?\s?I\.?|S\.?\s?A\.?\s?B\.?|S\.?\s?DE\s?R\.?\s?L\.?|S\.?\s?R\.?\s?L\.?|S\.?\s?C\.?|A\.?\s?C\.?|"
                     r"S\.?\s?P\.?\s?R\.?|S\.?\s?C\.?\s?L\.?|S\.?\s?C\.?\s?S\.?|SOCIEDAD|COOPERATIVA|S\.?\s?DE\s?S\.?\s?S\.?|INC\.?|LLC|LTD|"
                     r"C\.?\s?V\.?|GMBH|CORPORATION|CORP\.?|COMPANY)\b", re.I)


def _denue_rows(path, limit=None):
    z = zipfile.ZipFile(path)
    name = next(n for n in z.namelist() if n.lower().endswith(".csv") and "conjunto_de_datos" in n.lower() and "diccionario" not in n.lower())
    raw = z.read(name)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    rd = csv.DictReader(io.StringIO(text))
    log.info("BULK denue file %s, columns %s", name, ",".join(rd.fieldnames[:12]))
    for i, r in enumerate(rd):
        if limit and i >= limit * 40:
            break
        yield {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}


def denue(limit=None):
    tmp = tempfile.mkdtemp(prefix="denue-")
    path = download(DENUE_URL, os.path.join(tmp, "denue.zip"))
    seen = Counter()
    firms = {}
    for r in _denue_rows(path, limit):
        seen["rows"] += 1
        band = DENUE_BANDS.get(r.get("per_ocu", "").lower()) or DENUE_BANDS.get(fold(r.get("per_ocu", "")).lower())
        if not band:
            continue
        seen["51plus"] += 1
        legal = re.sub(r"\s+", " ", r.get("raz_social", "")).strip()
        if not legal:
            seen["empty_legal_name"] += 1
        if not legal or not MX_FORM.search(fold(legal)):
            seen["skipped_no_company_form"] += 1
            if legal and seen["skipped_no_company_form"] <= 25:
                log.info("BULK denue no-form tail: %s", " ".join(fold(legal).split()[-3:])[-30:])
            continue
        key = re.sub(r"[^a-z0-9]", "", fold(legal).lower())
        rank = {"51-100": 1, "101-250": 2, "251+": 3}[band]
        f = firms.get(key)
        if f is None:
            f = firms[key] = {"legal": legal, "estabs": 0, "rank": 0, "acts": Counter(), "best": None, "states": Counter(),
                              "web": "", "email": "", "phone": ""}
        f["estabs"] += 1; f["acts"][(r.get("codigo_act", ""), r.get("nombre_act", ""))] += 1; f["states"][r.get("entidad", "")] += 1
        if rank > f["rank"]:
            f["rank"], f["best"] = rank, r
        for k_, col in (("web", "www"), ("email", "correoelec"), ("phone", "telefono")):
            if not f[k_] and r.get(col):
                f[k_] = r[col]
        if limit and len(firms) >= limit:
            break
    out = []
    band_of = {1: "51-100", 2: "101-250", 3: "251+"}
    for f in firms.values():
        b = f["best"]
        acts = [n for (_, n), _c in f["acts"].most_common(3) if n]
        code = f["acts"].most_common(1)[0][0][0]
        street = title_case(" ".join(x for x in (b.get("tipo_vial", ""), b.get("nom_vial", ""), b.get("numero_ext", "")) if x and x.upper() != "NINGUNO"))
        addr = ", ".join(title_case(x) for x in (street, b.get("nomb_asent", ""), b.get("cod_postal", ""), b.get("municipio", ""), b.get("entidad", "")) if x)
        web = f["web"].strip()
        if web and not web.lower().startswith("http"):
            web = "http://" + web.lstrip("/")
        out.append({
            "supplier": title_case(f["legal"])[:150], "name_local": title_case(b.get("nom_estab", ""))[:150], "country": "MEX",
            "province": title_case(b.get("entidad", "")), "city": title_case(b.get("municipio", "")),
            "industry": f"{SCIAN3.get(code[:3], 'Manufacturing')} (SCIAN {code})"[:150], "products": "; ".join(acts)[:300],
            "website": web[:200], "email": f["email"].lower()[:120], "phone": f["phone"][:40], "address": addr[:250],
            "source": "INEGI DENUE (Mexico, manufacturing, 51+ employees)", "source_url": "https://www.inegi.org.mx/app/mapa/denue/",
            "notable": False, "basis": f"DENUE {b.get('id', '')}: SCIAN {code}, {band_of[f['rank']]} persons employed, {f['estabs']} establishment(s) of 51+",
            "employees": band_of[f["rank"]], "size_band": band_of[f["rank"]], "role": "manufacturer", "legal_id": "",
            "denue_id": b.get("id", ""), "scian": code, "establishments": f["estabs"],
        })
    log.info("BULK denue: %d rows read, %d with 51+ persons, %d without a company form skipped, %d companies",
             seen["rows"], seen["51plus"], seen["skipped_no_company_form"], len(out))
    return out, {"rows_read": seen["rows"], "establishments_51plus": seen["51plus"], "skipped_natural_person_or_no_form": seen["skipped_no_company_form"],
                 "licence": "INEGI Terminos de libre uso (attribution)", "url": DENUE_URL}


# ------------------------------------------------------------------------------------------------ Finland PRH / YTJ
PRH_URL = "https://avoindata.prh.fi/opendata-ytj-api/v3/all_companies"
PRH_PERSON_FORM = re.compile(r"toiminimi|elinkeinonharjoittaja|private trader|enskild n[äa]ringsidkare|sole trader", re.I)
PRH_SKIP_FORM = re.compile(r"asunto|housing|ulkomaisen|foreign|branch|sivuliike|filial|yhdistys|association|säätiö|foundation|"
                           r"kunta|municipal|valtio|state|seurakunta|parish", re.I)


def _desc(items, lang="3"):
    for d in items or []:
        if str(d.get("languageCode")) == lang:
            return d.get("description") or ""
    return (items or [{}])[0].get("description", "") if items else ""


def _prh_stream(path):
    """Companies from the all_companies zip, one at a time (ijson when available; a whole-file parse otherwise)."""
    z = zipfile.ZipFile(path)
    name = next(n for n in z.namelist() if n.lower().endswith(".json"))
    try:
        import ijson
        with z.open(name) as f:
            yield from ijson.items(f, "item")
    except ImportError:
        with z.open(name) as f:
            d = json.load(f)
        yield from (d if isinstance(d, list) else d.get("companies", []))


def prh(limit=None):
    tmp = tempfile.mkdtemp(prefix="prh-")
    path = download(PRH_URL, os.path.join(tmp, "prh.zip"))
    seen = Counter()
    out = []
    for c in _prh_stream(path):
        seen["companies"] += 1
        if c.get("endDate") or str(c.get("status") or "") not in ("2", "") and str(c.get("tradeRegisterStatus") or "") not in ("1",):
            seen["inactive"] += 1; continue
        mbl = c.get("mainBusinessLine") or {}
        code = str(mbl.get("type") or "")
        if not (code[:2].isdigit() and 10 <= int(code[:2]) <= 33):
            continue
        seen["manufacturing"] += 1
        forms = [f for f in (c.get("companyForms") or []) if not f.get("endDate")]
        form = _desc((forms or [{}])[0].get("descriptions"), "3") if forms else ""
        form_fi = _desc((forms or [{}])[0].get("descriptions"), "1") if forms else ""
        seen[f"form:{(forms or [{}])[0].get('type', '-') if forms else 'none'} {form_fi[:30]}"] += 1
        if not forms:
            seen["skipped_no_form"] += 1; continue  # a business without a company form is a sole trader (natural person)
        if PRH_PERSON_FORM.search(f"{form} {form_fi}"):
            seen["skipped_sole_trader"] += 1; continue
        if PRH_SKIP_FORM.search(f"{form} {form_fi}"):
            seen["skipped_other_form"] += 1; continue
        names = [n for n in (c.get("names") or []) if not n.get("endDate")]
        name = next((n["name"] for n in names if str(n.get("type")) == "1"), names[0]["name"] if names else "")
        if not name:
            continue
        addr = next((a for a in (c.get("addresses") or []) if str(a.get("type")) == "1"), None) or (c.get("addresses") or [{}])[0] if c.get("addresses") else {}
        city = ""
        if addr:
            city = next((p.get("city") for p in addr.get("postOffices") or [] if str(p.get("languageCode")) == "1"), "") or \
                (addr.get("postOffices") or [{}])[0].get("city", "") if addr.get("postOffices") else ""
        street = " ".join(str(x) for x in (addr.get("street"), addr.get("buildingNumber"), addr.get("entrance"), addr.get("apartmentNumber")) if x) if addr else ""
        web = ((c.get("website") or {}).get("url") or "").strip()
        if web and not web.lower().startswith("http"):
            web = "http://" + web
        bid = (c.get("businessId") or {}).get("value", "")
        act = _desc(mbl.get("descriptions"), "3")
        out.append({
            "supplier": name[:150], "name_local": "", "country": "FIN", "province": "", "city": (city or "").title(),
            "industry": f"TOL {code} {act}".strip()[:150], "products": act[:300], "website": web[:200], "email": "", "phone": "",
            "address": ", ".join(x for x in (street, (addr or {}).get("postCode", ""), (city or "").title()) if x)[:250],
            "source": "PRH/YTJ open data (Finland, manufacturing)", "source_url": f"https://tietopalvelu.ytj.fi/yritys/{bid}",
            "notable": False, "basis": f"Finnish business id {bid}; main line TOL {code}; {form or form_fi}",
            "employees": "", "size_band": "", "role": "manufacturer", "legal_id": f"FI {bid}" if bid else "", "company_form": form or form_fi,
            "registered": c.get("registrationDate", ""),
        })
        if limit and len(out) >= limit:
            break
    log.info("BULK prh: %s, %d manufacturers kept", dict(seen), len(out))
    return out, {**dict(seen), "licence": "CC BY 4.0 (Finnish Patent and Registration Office)", "url": PRH_URL}


# ------------------------------------------------------------------------------------------------ EU TRACES NT
TRACES = "https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication"
TRACES_UI = "https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/index#!/view"
TRACES_HDR = {"Accept": "application/json, text/plain, */*"}
MAKER_ACT = re.compile(r"process|plant|slaughter|cutting|manufactur|production|producer|packing|treatment|establishment|preparation|"
                       r"dairy|collection centre|purification|dispatch|factory|tannery|rendering|game handling|farm", re.I)
STORE_ACT = re.compile(r"cold store|storage|warehouse|re-?wrapping", re.I)


def _strings(o, keyrx, out):
    """Every 'translation' text under keys that match keyrx (activities, remarks, status), anywhere in the record."""
    if isinstance(o, dict):
        for k, v in o.items():
            if keyrx.search(k):
                _all_translations(v, out)
            else:
                _strings(v, keyrx, out)
    elif isinstance(o, list):
        for v in o:
            _strings(v, keyrx, out)


def _all_translations(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("translation", "value") and isinstance(v, str) and v.strip():
                out.append(v.strip())
            else:
                _all_translations(v, out)
    elif isinstance(o, list):
        for v in o:
            _all_translations(v, out)


def _countries():
    import pycountry
    return sorted(c.alpha_2 for c in pycountry.countries) + ["XK"]


def traces(limit=None):
    """Every country's establishment lists (one JSON call per country, one per country and section)."""
    from .gleif_bulk import iso2_to_3
    ops, seen = {}, Counter()
    first_keys = None
    secs = Counter()
    only_cc = [c for c in os.environ.get("BULK_COUNTRIES", "").split(",") if c]
    for cc in (only_cc or _countries()):
        try:
            r = fetch(f"{TRACES}?countryCode={cc}", pause=0.6, headers=TRACES_HDR, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("BULK traces %s: %s", cc, type(e).__name__); seen["country_errors"] += 1; continue
        if r.status_code != 200:
            seen[f"country_http_{r.status_code}"] += 1; continue
        try:
            lists = r.json()
        except ValueError:
            seen["country_not_json"] += 1; continue
        for L in lists or []:
            sec = L.get("classificationSectionId") or (L.get("establishmentListingId") or {}).get("classificationSectionId") or {}
            code, sec_name = sec.get("code"), sec.get("translation") or ""
            chapter = ((sec.get("classificationSectionChapter") or L.get("classificationSectionChapter") or {}).get("translation") or "")
            if not code or not L.get("numberOfEstablishments", 1):
                continue
            seen["lists"] += 1
            secs[(chapter, code, sec_name)] += L.get("numberOfEstablishments") or 0
            if re.search(r"vessel", sec_name, re.I):
                seen["vessel_lists_skipped"] += 1; continue  # a ship, not a company
            try:
                e = fetch(f"{TRACES}/establishments/{cc}/{code}", pause=0.8, headers=TRACES_HDR, timeout=120)
                ests = e.json() if e.status_code == 200 else []
            except Exception as ex:  # noqa: BLE001
                log.warning("BULK traces %s/%s: %s", cc, code, type(ex).__name__); seen["list_errors"] += 1; continue
            for x in ests or []:
                seen["establishments"] += 1
                if first_keys is None or (limit and seen["establishments"] % 97 == 1):
                    first_keys = sorted(x)
                    log.info("BULK traces record sample: %s", json.dumps({k: x.get(k) for k in ("operatorActivityTypes", "associatedOperatorActivityTypes", "productTypes", "category1", "category2", "category3", "remarks", "validTo")}, ensure_ascii=False)[:900])
                if x.get("confidential") or not x.get("operatorName"):
                    seen["confidential_skipped"] += 1; continue
                status = []
                _strings(x, re.compile(r"status", re.I), status)
                if any(re.search(r"suspend|withdraw|delist|revoked|inactive", t, re.I) for t in status):
                    seen["suspended_skipped"] += 1; continue
                acts = []
                _strings(x, re.compile(r"activit", re.I), acts)
                k = (cc, str(x.get("operatorId") or x["operatorName"]))
                o = ops.get(k)
                if o is None:
                    a = x.get("address") or {}
                    ref = a.get("cityReference") or {}
                    street = ((a.get("street") or {}).get("value") if isinstance(a.get("street"), dict) else a.get("street")) or ""
                    region = ((ref.get("region") or {}).get("translation") if isinstance(ref.get("region"), dict) else "") or ""
                    o = ops[k] = {"name": x["operatorName"], "cc": cc, "city": ref.get("name") or "", "postal": ref.get("postalCode") or "",
                                  "street": street, "region": region, "approvals": [], "sections": [], "chapters": [], "acts": []}
                if x.get("approvalNumber") and x["approvalNumber"] not in o["approvals"]:
                    o["approvals"].append(x["approvalNumber"])
                for lst_, v in ((o["sections"], sec_name), (o["chapters"], chapter)):
                    if v and v not in lst_:
                        lst_.append(v)
                for t in acts:
                    if t not in o["acts"] and len(t) < 80 and not re.fullmatch(r"(?i)active|valid|approved|yes|no|true|false|\d+", t):
                        o["acts"].append(t)
            if limit and len(ops) >= limit:
                break
        if limit and len(ops) >= limit:
            break
    out = []
    for (cc, _), o in ops.items():
        acts = "; ".join(o["acts"][:6])
        maker = bool(MAKER_ACT.search(acts)) or not acts or not STORE_ACT.search(acts)
        role = "manufacturer" if maker else "cold store / storage"
        ap = ", ".join(o["approvals"][:5])
        out.append({
            "supplier": title_case(o["name"])[:150], "name_local": "", "country": iso2_to_3(cc) or cc, "province": title_case(o["region"]),
            "city": title_case(o["city"]), "industry": "; ".join(dict.fromkeys(o["chapters"]))[:150] or "Food of animal origin",
            "products": "; ".join(o["sections"])[:300], "website": "", "email": "", "phone": "",
            "address": ", ".join(x for x in (title_case(o["street"]), o["postal"], title_case(o["city"])) if x)[:250],
            "source": "EU TRACES approved establishment", "source_url": f"{TRACES_UI}/{cc}",
            "notable": False, "basis": f"EU-approved establishment list ({'; '.join(o['sections'][:3])}), approval {ap}; activities: {acts}"[:300],
            "employees": "", "size_band": "", "role": role, "legal_id": "", "approval_no": ap, "activities": acts,
            "export_evidence": f"EU-approved establishment (TRACES), approval {ap}",
        })
    log.info("BULK traces: %s, %d operators", dict(seen), len(out))
    for (ch, code, nm), n in secs.most_common(80):
        log.info("BULK traces section %s | %s | %s | %d", ch, code, nm, n)
    return out, {**dict(seen), "licence": "Commission Decision 2011/833/EU reuse (attribution)", "url": TRACES}


# ------------------------------------------------------------------------------------------------ USDA FSIS
FSIS_PAGE = "https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory"


def fsis(limit=None):
    r = fetch(FSIS_PAGE)  # raises PermissionError when robots.txt cannot be read (403)
    if r.status_code != 200:
        raise PermissionError(f"FSIS directory page answers {r.status_code} to automated clients; not worked around")
    links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|csv))"', r.text, re.I)))
    raise NotImplementedError(f"FSIS file links found: {links[:5]}")


SOURCES = {"traces": traces, "denue": denue, "fsis": fsis, "prh": prh}


# ------------------------------------------------------------------------------------------------ seal and status
def counts(rows):
    n = len(rows)
    by_c = Counter(r.get("country") or "?" for r in rows)
    return {"records": n, "manufacturers": sum(1 for r in rows if r.get("role") in ("manufacturer", "producer")),
            "medium_plus": sum(1 for r in rows if r.get("size_band") in ("51-100", "101-250", "251+")),
            "with_website": sum(1 for r in rows if r.get("website")), "with_email": sum(1 for r in rows if r.get("email")),
            "with_phone": sum(1 for r in rows if r.get("phone")), "with_legal_id": sum(1 for r in rows if r.get("legal_id")),
            "with_approval_no": sum(1 for r in rows if r.get("approval_no")), "with_address": sum(1 for r in rows if r.get("address")),
            "countries": len(by_c), "top_countries": dict(by_c.most_common(15))}


def seal_rows(name, rows):
    """Sealed with the import public key into data/import/bulk-<name>.enc; skipped when the content is unchanged."""
    from .importer import seal
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in sorted(rows, key=lambda r: (r.get("country", ""), r.get("supplier", ""))))
    h = hashlib.sha256(body.encode()).hexdigest()[:16]
    st = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    if (st.get(name) or {}).get("hash") == h and (IMPORT_DIR / f"bulk-{name}.enc").exists():
        log.info("BULK %s: unchanged (%s), drop not rewritten", name, h); return h, False
    fd, tmp = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    seal(tmp, f"bulk-{name}")
    os.unlink(tmp)
    return h, True


def run(names, limit=None):
    st = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    for n in names:
        t0 = time.time()
        try:
            rows, meta = SOURCES[n](limit)
        except Exception as e:  # noqa: BLE001
            log.warning("BULK %s failed: %s: %s", n, type(e).__name__, str(e)[:300])
            st[n] = {**(st.get(n) or {}), "last_error": f"{type(e).__name__}: {str(e)[:200]}", "last_try": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
            continue
        c = counts(rows)
        if limit:
            log.info("BULK %s test (--limit %s): %s", n, limit, json.dumps(c))
            log.info("BULK %s sample: %s", n, json.dumps([{k: r.get(k) for k in ("supplier", "country", "city", "industry", "size_band", "approval_no")} for r in rows[:5]], ensure_ascii=False))
            continue
        h, wrote = seal_rows(n, rows)
        st[n] = {**c, **meta, "hash": h, "sealed_now": wrote, "seconds": round(time.time() - t0),
                 "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "last_error": ""}
        log.info("BULK %s: %s", n, json.dumps(c))
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(st, indent=1, ensure_ascii=False))
    return st


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    a = sys.argv[1:]
    if a[:1] == ["run"]:
        sel = a[1] if len(a) > 1 else "all"
        names = list(SOURCES) if sel in ("all", "") else [x.strip() for x in sel.split(",") if x.strip()]
        lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
        if "--countries" in a:
            os.environ["BULK_COUNTRIES"] = a[a.index("--countries") + 1]
        run(names, lim)
