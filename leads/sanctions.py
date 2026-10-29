"""Sanctions and country-risk screen for tenders (runs in the merge, after the deal engine).

Country level: data/leads/country_risk.csv (block = no Pursue/Watch; restricted = at most Watch, with the reason).
Entity level: buyers matched against official lists of sanctioned entities (not individuals):
  OFAC SDN (US Treasury), UN Security Council consolidated list, EU financial sanctions list.
Lists are downloaded once a day (cache data/leads/cache/sanctions.json). Matching is conservative (exact normalised
name, or a long listed name contained in the buyer name) and a match is a flag to check, not a legal finding.
"""
import csv
import io
import json
import re
import xml.etree.ElementTree as ET

from .common import LEADS, log, session, today

CACHE = LEADS / "cache" / "sanctions.json"
RISK = LEADS / "country_risk.csv"
OFAC = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
UN = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
EU = "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
SUFFIX = r"\b(the|ltd|llc|limited|co|company|corp|corporation|inc|jsc|ojsc|pjsc|cjsc|sa|s a|gmbh|plc|fze|fzco|llp|ooo|zao|oao)\b"


GENERIC = re.compile(r"^(ministry|department|government|state|national|central|federal|office|agency|bank|committee|council|directorate|general|empresa|compa[nñ]ia|sociedad|ministerio|minist[eè]re|ministero|ministerstvo|corporaci[oó]n|instituto|servicio)\b")


HOME_OF_LISTS = {"AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA",
                 "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE", "NOR", "ISL", "LIE", "CHE",
                 "GBR", "USA", "CAN", "AUS", "NZL", "JPN", "KOR", "ISR"}


def norm(s):
    s = re.sub(r"[^a-z0-9Ѐ-ӿ؀-ۿ ]+", " ", (s or "").lower())
    return re.sub(r"\s+", " ", re.sub(SUFFIX, " ", s)).strip()


def _ofac(s):
    r = s.get(OFAC, timeout=120); r.raise_for_status()
    out = []
    for row in csv.reader(io.StringIO(r.content.decode("latin-1"))):
        if len(row) > 3 and row[2].strip().strip('"').lower() != "individual":
            out.append([row[1].strip(), "OFAC SDN " + row[3].strip()[:40]])
    return out


def _un(s):
    r = s.get(UN, timeout=120); r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for e in root.iter("ENTITY"):
        name = (e.findtext("FIRST_NAME") or "").strip()
        ref = (e.findtext("REFERENCE_NUMBER") or "").strip()
        if name:
            out.append([name, "UN " + ref])
        for a in e.iter("ENTITY_ALIAS"):
            an = (a.findtext("ALIAS_NAME") or "").strip()
            if an and len(an) > 6:
                out.append([an, "UN " + ref])
    return out


def _eu(s):
    r = s.get(EU, timeout=120); r.raise_for_status()
    rows = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", "replace")), delimiter=";")
    out = []
    for x in rows:
        if (x.get("Entity_SubjectType") or x.get("Entity_SubjectType_Code") or "").lower().startswith("e"):
            n = x.get("NameAlias_WholeName") or ""
            lang = (x.get("NameAlias_NameLanguage") or "").upper()
            if n and lang in ("", "EN"):  # the EU list repeats names in every EU language ("Ministry of Defence" ...)
                out.append([n, "EU " + (x.get("Entity_Programme") or "")[:20]])
    return out


def load_lists():
    c = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if c.get("date") == str(today()):
        return c
    s = session()
    for name, fn in (("ofac", _ofac), ("un", _un), ("eu", _eu)):
        try:
            c[name] = fn(s)
        except Exception as e:  # noqa: BLE001 - keep yesterday's copy of a list that fails today
            log.warning("sanctions %s: %s", name, str(e)[:160])
    c["date"] = str(today())
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, ensure_ascii=False))
    return c


def screen(tenders):
    risk = {r["iso3"]: r for r in csv.DictReader(open(RISK, encoding="utf-8"))} if RISK.exists() else {}
    lists = load_lists()
    exact, long_names = {}, []
    for k in ("ofac", "un", "eu"):
        for name, src in lists.get(k) or []:
            n = norm(name)
            if len(n) < 6 or (GENERIC.match(n) and len(n.split()) <= 5):
                continue  # "ministry of defence" alone would flag every country's ministry
            exact.setdefault(n, src)
            if len(n) >= 15 and len(n.split()) >= 2:
                long_names.append((n, src))
    by_tok = {}  # long listed names indexed by their first word, so each buyer is compared with a handful only
    for n, src in long_names:
        by_tok.setdefault(n.split()[0], []).append((n, src))
    stats = {"country_block": 0, "country_restricted": 0, "entity": 0, "listed_names": len(exact)}
    for t in tenders:
        note = ""
        rk = risk.get(t.get("country", ""))
        b = norm(t.get("buyer"))
        hit = exact.get(b) if b else None
        if not hit and b and len(b) >= 15:
            pb = f" {b} "
            hit = next((src for tok in set(b.split()) for n, src in by_tok.get(tok, ()) if f" {n} " in pb), None)
        if hit and t.get("country") in HOME_OF_LISTS:
            hit = None  # a public body of an EU/G7/allied state is not on these lists: same-name false match
        if hit:
            t["decision"] = "Ignore"; note = f"SANCTIONS: buyer matches {hit} - check before any contact"
            stats["entity"] += 1
            if stats["entity"] <= 15:
                log.info("sanctions hit: %s (%s) ~ %s", t.get("buyer"), t.get("country"), hit)
        elif rk and rk["level"] == "block":
            t["decision"] = "Ignore"; note = f"BLOCKED: {rk['reason']}"
            stats["country_block"] += 1
        elif rk and rk["level"] == "restricted":
            if t.get("decision") == "Pursue":
                t["decision"] = "Watch"
            note = f"RESTRICTED: {rk['reason']}"
            stats["country_restricted"] += 1
        if note:
            t["why"] = (note + "; " + (t.get("why") or ""))[:300]
    log.info("sanctions screen: %s", stats)
    return stats
