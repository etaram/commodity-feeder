"""Identity checks against official registers, in code: the supplier's legal name, registered address and status as
the register holds them, with the register record as evidence.

  GLEIF (LEI register, free, about 60 requests a minute): every legal entity with an LEI, worldwide. A record counts as
        the company's only when its legal name matches (after legal suffixes) and its legal address is in the same
        country. A leiCode the company's own site publishes is looked up directly.
  VIES (EU VAT validation, free): a VAT number found on the company's own site or on record, for EU countries; the
        register says valid or not, and for most member states returns the registered name and address.

Verdicts per company: "verified" (an active register record, exact name, same country), "likely" (name close, same
country), "not found", "conflict" (the register record is inactive, or the number belongs to another name).
Nothing is marked verified without the register record; the evidence URL is kept with the date.
Queue: companies whose website check read correctly first (their own site is the strongest claim to check), then
proven suppliers; each company is rechecked after RECHECK_DAYS. Budget: --minutes (default 15) per run.
Output: data/checks/registry_checks.jsonl (one line per company), the private sheet tab 'Registry checks'.
Run: python -m leads.registry_check --minutes 15"""
import csv
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

from .common import DATA, PRIVATE, log

CHECKS = DATA / "checks"
OUT = CHECKS / "registry_checks.jsonl"
COMPANY_CHECKS = CHECKS / "company_checks.jsonl"
VERSION = "registry-2"
RECHECK_DAYS = 180
GLEIF = "https://api.gleif.org/api/v1/lei-records"
VIES = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{num}"
UA = "Mozilla/5.0 (compatible; SinderRegistryCheck/1.0; +https://github.com/etaram/commodity-feeder)"
EU = {"AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CYP": "CY", "CZE": "CZ", "DNK": "DK", "EST": "EE", "FIN": "FI", "FRA": "FR",
      "DEU": "DE", "GRC": "EL", "HUN": "HU", "IRL": "IE", "ITA": "IT", "LVA": "LV", "LTU": "LT", "LUX": "LU", "MLT": "MT", "NLD": "NL",
      "POL": "PL", "PRT": "PT", "ROU": "RO", "SVK": "SK", "SVN": "SI", "ESP": "ES", "SWE": "SE"}
LEGAL = re.compile(r"\b(s\.?a\.?s?|s\.?a\.?u|ltda|ltd|limited|llc|inc|incorporated|gmbh|ag|kg|co\.? ?kg|srl|s\.?r\.?l|spa|s\.?p\.?a|bv|b\.v|nv|"
                   r"plc|pty|pvt|private|public|co|corp|corporation|company|sp\.? ?z\.? ?o\.? ?o|s\.?a\.? de c\.?v|sarl|sas|ab|as|a/s|oy|oyj|"
                   r"kft|zrt|d\.?o\.?o|a\.?s|s\.?r\.?o|jsc|pjsc|ooo|llp|lp|se|eirl|eurl|ug|e\.?k|ohg|gbr|bhd|sdn|tbk|pt|cv)\b\.?", re.I)


# legal forms written out in full, as registers often print them (after accents are removed)
LEGAL_LONG = re.compile(r"\b(societa per azioni|societa a responsabilita limitata|spolka z ograniczona odpowiedzialnoscia|spolka akcyjna|spolka komandytowa|"
                        r"aktiengesellschaft|gesellschaft mit beschrankter haftung|kommanditgesellschaft|aktiebolag|aktieselskab|anpartsselskab|"
                        r"osakeyhtio|sociedad anonima|sociedad limitada|sociedade anonima|societe anonyme|societe par actions simplifiee|"
                        r"societe a responsabilite limitee|naamloze vennootschap|besloten vennootschap|anonim sirketi|spolecnost s rucenim omezenym|"
                        r"akciova spolecnost|societate comerciala|unipessoal|sociedad anonima unipersonal|sociedad limitada unipersonal)\b", re.I)


def norm(n):
    import html
    import unicodedata
    n = unicodedata.normalize("NFKD", html.unescape(n or "").translate(str.maketrans("łŁøØđĐßæÆ", "lLoOdDsaA"))).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    n = re.sub(r"\s+", " ", re.sub(r"[^\w\s/]", " ", n.replace("'", "")))
    n = LEGAL.sub(" ", LEGAL_LONG.sub(" ", n))
    return re.sub(r"\s+", " ", re.sub(r"\band\b", " ", n)).strip()


def name_score(a, b):
    """1.0 for the same name after legal suffixes; token overlap otherwise (pure)."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb or na.replace(" ", "") == nb.replace(" ", ""):
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    return len(ta & tb) / max(1, len(ta | tb))


_ISO2 = {}


def iso2(iso3):
    if not _ISO2:
        try:
            import pycountry
            for c in pycountry.countries:
                _ISO2[c.alpha_3] = c.alpha_2
        except Exception:  # noqa: BLE001
            pass
        _ISO2.setdefault("XKX", "XK")
    return _ISO2.get(iso3, "")


def vat_parts(v, country):
    """('DE', '123456789') from a VAT number as printed, for an EU country (pure)."""
    v = re.sub(r"[\s.\-]", "", (v or "").upper())
    cc = EU.get(country, "")
    if not cc:
        return None
    if v.startswith(("EL", "GR")) and cc == "EL":
        v = v[2:]
    elif v[:2] == cc:
        v = v[2:]
    elif re.match(r"^[A-Z]{2}", v):
        return None  # another country's prefix: not this company's EU number
    if cc == "SE" and re.fullmatch(r"\d{10}", v):
        v += "01"  # a Swedish VAT number is the organisation number followed by 01
    return (cc, v) if re.fullmatch(r"[0-9A-Z]{8,12}", v) else None


def judge_lei(name, country, rec):
    """Verdict for one GLEIF record against the company on record (pure). rec: the API's data item."""
    a = rec.get("attributes") or {}
    ent = a.get("entity") or {}
    legal = (ent.get("legalName") or {}).get("name") or ""
    others = [x.get("name") or "" for x in ent.get("otherNames") or []]
    sc = max([name_score(name, legal)] + [name_score(name, o) for o in others])
    la = ent.get("legalAddress") or {}
    same_country = bool(country) and la.get("country") == iso2(country)
    active = ent.get("status") == "ACTIVE"
    reg = (a.get("registration") or {}).get("status") or ""
    addr = ", ".join(x for x in [" ".join(la.get("addressLines") or []), la.get("postalCode") or "", la.get("city") or "", la.get("country") or ""] if x)
    out = {"lei": rec.get("id") or a.get("lei") or "", "legal_name": legal[:150], "register_address": addr[:250], "register_country": la.get("country") or "",
           "entity_status": ent.get("status") or "", "lei_status": reg, "registered_as": (ent.get("registeredAs") or "")[:40],
           "legal_form": ((ent.get("legalForm") or {}).get("id") or "")[:10], "name_score": round(sc, 2),
           "evidence": f"https://search.gleif.org/#/record/{rec.get('id') or a.get('lei')}"}
    if sc >= 1.0 and same_country and active:
        out["verdict"] = "verified"
    elif sc >= 1.0 and same_country and not active:
        out["verdict"] = "conflict"; out["why"] = f"the register shows the entity as {ent.get('status')}"
    elif sc >= 0.75 and same_country:
        out["verdict"] = "likely"
    else:
        out["verdict"] = "not found"
    return out


def judge_vies(name, j, printed_as_vat=True):
    """Verdict for a VIES answer (pure): the number is valid, and the registered name, where returned, matches."""
    if not j or "isValid" not in j:
        return {"vat_verdict": "unavailable"}
    reg_name = (j.get("name") or "").strip()
    reg_name = "" if reg_name in ("---", "") else reg_name
    out = {"vat_valid": bool(j.get("isValid")), "vat_name": reg_name[:150], "vat_address": re.sub(r"\s+", " ", j.get("address") or "").strip()[:250].replace("---", "")}
    if not j.get("isValid"):
        # a registration number on record is not always a VAT number: invalid then says nothing about identity
        out["vat_verdict"] = "invalid" if printed_as_vat else "not a VAT number in VIES"
    elif not reg_name:
        out["vat_verdict"] = "valid (the register returns no name for this country)"
    else:
        sc = name_score(name, reg_name)
        out["vat_verdict"] = "verified" if sc >= 1.0 else "likely" if sc >= 0.34 else "conflict"
        if out["vat_verdict"] == "conflict":
            out["why"] = f"the VAT number is registered to {reg_name[:80]}"
    return out


# ---------------------------------------------------------------- network
def _session():
    import requests
    s = requests.Session(); s.headers["User-Agent"] = UA
    return s


def _get_json(s, url, params=None, accept="application/json"):
    for i in range(3):
        try:
            r = s.get(url, params=params, timeout=30, headers={"Accept": accept})
            if r.status_code == 429:
                time.sleep(10 * (i + 1)); continue
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return None


def lei_lookup(s, name, country, lei=""):
    if lei and re.fullmatch(r"[A-Z0-9]{20}", lei):
        j = _get_json(s, f"{GLEIF}/{lei}", accept="application/vnd.api+json")
        recs = [j["data"]] if j and j.get("data") else []
    else:
        params = {"filter[entity.legalName]": name[:120], "page[size]": 5}
        if iso2(country):
            params["filter[entity.legalAddress.country]"] = iso2(country)
        j = _get_json(s, GLEIF, params, accept="application/vnd.api+json")
        recs = (j or {}).get("data") or []
        if not recs and iso2(country):  # legal names are often written differently: full-text search in the same country
            time.sleep(1.1)
            j = _get_json(s, GLEIF, {"filter[fulltext]": norm(name)[:100] or name[:100], "filter[entity.legalAddress.country]": iso2(country), "page[size]": 5},
                          accept="application/vnd.api+json")
            recs = (j or {}).get("data") or []
    if j is None:
        return None
    best = None
    for rec in recs:
        v = judge_lei(name, country, rec)
        rank = {"verified": 3, "conflict": 2, "likely": 1}.get(v["verdict"], 0)
        if not best or rank > best[0] or (rank == best[0] and v["name_score"] > best[1]["name_score"]):
            best = (rank, v)
    if not best or best[0] == 0:
        return {"verdict": "not found", "source": "GLEIF"}
    return {**best[1], "source": "GLEIF"}


# ---------------------------------------------------------------- queue
def load(p):
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line); out[d["key"]] = d
            except (ValueError, KeyError):
                pass
    return out


def site_ids(check):
    ids = {x.get("kind"): x.get("value") for x in (check or {}).get("legal_ids") or []}
    st = (check or {}).get("structured") or {}
    return {"vat": st.get("vat") or ids.get("VAT") or "", "lei": st.get("lei") or ids.get("LEI") or ""}


def queue(rows, checks, done, today):
    stale = (today - timedelta(days=RECHECK_DAYS)).isoformat()
    due = lambda k: k not in done or str(done[k].get("checked", "")) < stale or done[k].get("version") != VERSION  # noqa: E731
    by_key = {f"{r['supplier']}|{r['country']}": r for r in rows}
    first = [k for k, c in sorted(checks.items(), key=lambda kv: kv[1].get("checked", ""), reverse=True)
             if c.get("verdict") == "ok" and c.get("name_match") in ("high", "partial") and k in by_key]
    proven = [f"{r['supplier']}|{r['country']}" for r in rows if r.get("tier") in ("1", "2")]
    seen, out = set(), []
    for k in first + proven:
        if k not in seen and due(k) and by_key[k].get("country"):
            seen.add(k); out.append(by_key[k])
    return out


def check_one(s, r, check):
    name, cty = r["supplier"], r["country"]
    ids = site_ids(check)
    rec_vat = r.get("legal_id") if vat_parts(r.get("legal_id") or "", cty) else ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    out = {"key": f"{name}|{cty}", "supplier": name, "country": cty, "checked": now[:10], "version": VERSION}
    lei = lei_lookup(s, name, cty, ids["lei"])
    if lei is None:
        return None  # register unreachable: try again next run
    out.update(lei)
    vat = ids["vat"] or rec_vat
    vp = vat_parts(vat, cty)
    if vp:
        time.sleep(1.0)
        j = _get_json(s, VIES.format(cc=vp[0], num=vp[1]))
        out.update({"vat": f"{vp[0]}{vp[1]}", "vat_from": "company website" if ids["vat"] else "record", **judge_vies(name, j, printed_as_vat=bool(ids["vat"])),
                    "vat_evidence": "https://ec.europa.eu/taxation_customs/vies/"})
    # overall identity verdict: a register record or a valid VAT number in the company's name
    v = out.get("verdict"), out.get("vat_verdict", "")
    out["identity"] = ("verified" if "verified" in v or out.get("vat_verdict") == "verified"
                       else "conflict" if "conflict" in v or out.get("vat_verdict") in ("conflict", "invalid")
                       else "likely" if "likely" in v or out.get("vat_verdict") == "likely" else "not found")
    return out


def push_sheet(done):
    try:
        from .push import UNIVERSE_SHEET, Sheets
    except Exception:  # noqa: BLE001
        return
    head = ["key", "supplier", "country", "checked", "identity", "source", "lei", "legal_name", "register_address", "entity_status", "lei_status",
            "registered_as", "name_score", "evidence", "vat", "vat_from", "vat_verdict", "vat_name", "vat_address", "why", "version"]
    rows = [head] + [[str(d.get(h, "")) for h in head] for d in sorted(done.values(), key=lambda d: d.get("checked", ""), reverse=True)[:40000]]
    try:
        Sheets().replace_tab(UNIVERSE_SHEET, "Registry checks", rows, raw=True)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        log.warning("registry checks: sheet not written (%s)", str(e)[:120])


def main(minutes=15):
    src = PRIVATE / "universe.csv"
    if not src.exists():
        log.info("registry check: no universe yet"); return {}
    CHECKS.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    checks, done = load(COMPANY_CHECKS), load(OUT)
    todo = queue(rows, checks, done, date.today())
    s, deadline, n = _session(), time.time() + minutes * 60, 0
    stats = {}
    with open(OUT, "a", encoding="utf-8") as f:
        for r in todo:
            if time.time() > deadline:
                break
            res = check_one(s, r, checks.get(f"{r['supplier']}|{r['country']}"))
            time.sleep(1.1)  # GLEIF allows about 60 requests a minute
            if not res:
                continue
            done[res["key"]] = res; n += 1
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            stats[res["identity"]] = stats.get(res["identity"], 0) + 1
    OUT.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in done.values()), encoding="utf-8")
    push_sheet(done)
    tot = {}
    for d in done.values():
        tot[d.get("identity")] = tot.get(d.get("identity"), 0) + 1
    log.info("registry check: %d queued, %d checked this run %s; on record %s", len(todo), n, stats, tot)
    return {"queued": len(todo), "checked": n, **stats}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    a = sys.argv[1:]
    print(main(int(a[a.index("--minutes") + 1]) if "--minutes" in a else 15))
