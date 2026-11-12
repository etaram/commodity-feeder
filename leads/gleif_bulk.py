"""GLEIF Golden Copy bulk match (CC0, https://www.gleif.org/en/about/open-data): the Level 1 LEI-CDF concatenated
file (~3.5 million legal entities) and the Level 2 relationship file (direct and ultimate accounting parents), read
as streams from the downloaded zips, matched to the supplier universe by normalised legal name + country.

Per matched supplier: LEI, legal name, registration authority id (RA code and the entity's id in that register),
legal address city, entity status, and the direct / ultimate parent (LEI and name) where Level 2 has one.
A name that maps to more than one active LEI in the same country is not matched (ambiguous; counted).

Output (never published): data/gleif/matches.jsonl, kept in the Actions cache "gleif-" and read by leads/universe.py.
Public: counts only in the log. A sample of 50 matches for the precision check is sealed to the review key
(leads/source_cycle.py) and, when the sheet is configured, written to the private Supplier Universe sheet tab
"GLEIF precision". The zips are deleted after the run.

  python -m leads.gleif_bulk [--max-age-days 7] [--universe data/private/universe.csv]"""
import csv
import datetime as dt
import functools
import io
import json
import os
import random
import re
import sys
import tempfile
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict

from .common import DATA, PRIVATE, log

API = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest"
DIR = DATA / "gleif"
OUT = DIR / "matches.jsonl"
STATE = DIR / "state.json"
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
FORMS = {
    "ltd", "limited", "llc", "l l c", "inc", "incorporated", "corp", "corporation", "co", "company", "plc", "pty", "pte", "pvt", "private",
    "sa", "s a", "sas", "sarl", "sa de cv", "de cv", "s de rl", "srl", "s r l", "spa", "s p a", "sl", "s l", "slu", "ltda", "eireli", "me", "epp",
    "gmbh", "ag", "kg", "gmbh co kg", "co kg", "ug", "ohg", "bv", "nv", "b v", "n v", "ab", "oy", "oyj", "as", "a s", "asa", "aps", "a/s",
    "kft", "zrt", "nyrt", "sp z o o", "sp zoo", "spzoo", "s c", "sro", "s r o", "as", "doo", "d o o", "jsc", "ojsc", "pjsc", "cjsc", "ooo", "oao", "zao",
    "pao", "tov", "llp", "lp", "fze", "fzco", "fz llc", "wll", "w l l", "spc", "saog", "saoc", "bsc", "qsc", "psc", "pjsc", "sae", "s a e",
    "tbk", "pt", "bhd", "sdn bhd", "sdn", "berhad", "jsc", "co ltd", "company limited", "the", "se", "kk", "k k",
    "gk", "yk", "cv", "c v", "ci", "sasu", "eurl", "sca", "scs", "snc", "cooperative", "coop", "ltda me", "ltda epp", "ab publ", "publ",
}
_NON = re.compile(r"[^a-z0-9 ]+")
_SP = re.compile(r"\s+")


def norm_name(s):
    """lower-case ASCII, punctuation out, trailing legal forms out ('Siemens Aktiengesellschaft' stays distinct from
    'Siemens'; 'ACME Trading Co., Ltd.' -> 'acme trading')."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " ")
    s = _SP.sub(" ", _NON.sub(" ", s)).strip()
    words = s.split()
    changed = True
    while words and changed:
        changed = False
        for n in (3, 2, 1):
            if len(words) > n and " ".join(words[-n:]) in FORMS:
                words = words[:-n]; changed = True; break
        if words and len(words) > 1 and words[0] in ("pt", "the", "cv", "ooo", "tov", "pao", "oao", "zao"):
            words = words[1:]; changed = True
    return " ".join(words)


@functools.lru_cache(maxsize=512)
def iso2_to_3(c):
    try:
        import pycountry
        return pycountry.countries.get(alpha_2=c).alpha_3 if c else ""
    except Exception:  # noqa: BLE001
        return {"XK": "XKX"}.get(c, "")


def _col(header, *names):
    for n in names:
        if n in header:
            return header.index(n)
    return None


def universe_keys(path):
    """{norm|ISO3: [supplier key, ...]} from the private universe (supplier key = 'supplier|country')."""
    csv.field_size_limit(10 ** 8)
    idx = defaultdict(list)
    meta = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            n, c = norm_name(r.get("supplier")), (r.get("country") or "")[:3].upper()
            if len(n) < 3 or not c:
                continue
            k = f"{r['supplier']}|{r['country']}"
            idx[f"{n}|{c}"].append(k)
            meta[k] = {"website": r.get("website", ""), "address": (r.get("address") or "")[:120], "region": r.get("region", "")}
    return idx, meta


def read_rr(zpath):
    """{child LEI: {"direct": LEI, "ultimate": LEI}} for active accounting-consolidation relationships."""
    out = defaultdict(dict)
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as fb:
            rd = csv.reader(io.TextIOWrapper(fb, encoding="utf-8", newline=""))
            h = next(rd)
            s, e, t = _col(h, "Relationship.StartNode.NodeID"), _col(h, "Relationship.EndNode.NodeID"), _col(h, "Relationship.RelationshipType")
            st = _col(h, "Relationship.RelationshipStatus")
            for row in rd:
                if st is not None and row[st] != "ACTIVE":
                    continue
                typ = row[t]
                if typ == "IS_DIRECTLY_CONSOLIDATED_BY":
                    out[row[s]]["direct"] = row[e]
                elif typ == "IS_ULTIMATELY_CONSOLIDATED_BY":
                    out[row[s]]["ultimate"] = row[e]
    return out


def match_lei2(rows, idx, rr):
    """One pass over Level 1 rows (header first). Returns (matches {supplier key: rec}, parent names, stats)."""
    rows = iter(rows)
    h = next(rows)
    c_lei, c_name = _col(h, "LEI"), _col(h, "Entity.LegalName")
    c_ctry = _col(h, "Entity.LegalAddress.Country")
    c_hq = _col(h, "Entity.HeadquartersAddress.Country")
    c_city = _col(h, "Entity.LegalAddress.City")
    c_ra = _col(h, "Entity.RegistrationAuthority.RegistrationAuthorityID")
    c_raid = _col(h, "Entity.RegistrationAuthority.RegistrationAuthorityEntityID")
    c_status = _col(h, "Entity.EntityStatus")
    c_reg = _col(h, "Registration.RegistrationStatus")
    c_other = [i for i, x in enumerate(h) if re.match(r"Entity\.(OtherEntityNames\.OtherEntityName|TransliteratedOtherEntityNames\.TransliteratedOtherEntityName)\.\d+$", x)][:6]
    parents_needed = {p for v in rr.values() for p in v.values()}
    cand = defaultdict(list)   # supplier key -> [rec]
    pnames = {}
    stats = Counter()
    for row in rows:
        stats["lei_records"] += 1
        lei = row[c_lei]
        if lei in parents_needed:
            pnames[lei] = row[c_name]
        if c_status is not None and row[c_status] != "ACTIVE":
            continue
        ctrys = {iso2_to_3(row[c_ctry])} | ({iso2_to_3(row[c_hq])} if c_hq is not None else set())
        names = {norm_name(row[c_name])} | {norm_name(row[i]) for i in c_other if row[i]}
        hit = False
        for n in names:
            if len(n) < 3:
                continue
            for c in ctrys:
                for k in idx.get(f"{n}|{c}", ()):
                    hit = True
                    cand[k].append({"lei": lei, "legal_name": row[c_name], "city": row[c_city] if c_city is not None else "",
                                    "ra": row[c_ra] if c_ra is not None else "", "ra_entity_id": row[c_raid] if c_raid is not None else "",
                                    "registration": row[c_reg] if c_reg is not None else "", "matched_on": "legal name" if n == norm_name(row[c_name]) else "other name"})
        stats["active_matched_any"] += hit
    matches = {}
    for k, lst in cand.items():
        leis = {x["lei"] for x in lst}
        if len(leis) > 1:
            stats["ambiguous"] += 1
            continue
        m = lst[0]
        p = rr.get(m["lei"]) or {}
        m["parent_lei"], m["ultimate_parent_lei"] = p.get("direct", ""), p.get("ultimate", "")
        matches[k] = m
    for m in matches.values():
        m["parent_name"] = pnames.get(m["parent_lei"], "")
        m["ultimate_parent_name"] = pnames.get(m["ultimate_parent_lei"], "")
    stats["matched"] = len(matches)
    stats["with_parent"] = sum(1 for m in matches.values() if m["parent_lei"] or m["ultimate_parent_lei"])
    return matches, stats


def _download(s, url, dest):
    with s.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return os.path.getsize(dest)


def _lei2_rows(zpath):
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as fb:
            yield from csv.reader(io.TextIOWrapper(fb, encoding="utf-8", newline=""))


def precision_sample(matches, meta, n=50, seed=7):
    keys = sorted(matches)
    random.Random(seed).shuffle(keys)
    out = []
    for k in keys[:n]:
        m, u = matches[k], meta.get(k, {})
        sup, ctry = k.rsplit("|", 1)
        city_hit = bool(m["city"]) and m["city"].lower() in (u.get("address") or "").lower()
        out.append({"supplier": sup, "country": ctry, "website": u.get("website", ""), "address": u.get("address", ""),
                    "lei": m["lei"], "legal_name": m["legal_name"], "lei_city": m["city"], "ra": m["ra"], "ra_entity_id": m["ra_entity_id"],
                    "matched_on": m["matched_on"], "city_in_address": city_hit, "ultimate_parent": m.get("ultimate_parent_name", "")})
    return out


def run(max_age_days=7, universe=None, force=False):
    import requests
    universe = universe or PRIVATE / "universe.csv"
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not force and OUT.exists() and st.get("run", "") >= str(dt.date.today() - dt.timedelta(days=max_age_days)):
        log.info("gleif bulk: fresh (%s), nothing to do", st.get("run"))
        return {"note": "fresh"}
    if not universe.exists():
        log.warning("gleif bulk: no universe file"); return {"note": "no universe"}
    s = requests.Session(); s.headers["User-Agent"] = UA
    pub = s.get(API, timeout=60).json()["data"]
    t0 = time.time()
    idx, meta = universe_keys(universe)
    tmp = tempfile.mkdtemp(prefix="gleif")
    try:
        zrr, zl1 = os.path.join(tmp, "rr.zip"), os.path.join(tmp, "lei2.zip")
        n_rr = _download(s, pub["rr"]["full_file"]["csv"]["url"], zrr)
        rr = read_rr(zrr); os.remove(zrr)
        n_l1 = _download(s, pub["lei2"]["full_file"]["csv"]["url"], zl1)
        matches, stats = match_lei2(_lei2_rows(zl1), idx, rr)
    finally:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)
    DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for k, m in matches.items():
            f.write(json.dumps({"key": k, **m}, ensure_ascii=False) + "\n")
    by_region = Counter((meta.get(k) or {}).get("region") or "unknown" for k in matches)
    stats.update({"universe_names": len(idx), "relationships": len(rr), "zip_mb": round((n_rr + n_l1) / 1e6),
                  "publish": pub.get("publish_date", ""), "minutes": round((time.time() - t0) / 60, 1)})
    STATE.write_text(json.dumps({"run": str(dt.date.today()), "stats": dict(stats), "by_region": dict(by_region)}))
    sample = precision_sample(matches, meta)
    try:
        from .source_cycle import save_sealed
        save_sealed("gleif_precision_sample", json.dumps(sample, ensure_ascii=False, indent=1))
    except Exception as e:  # noqa: BLE001
        log.warning("gleif sample not sealed: %s", type(e).__name__)
    try:
        from .push import UNIVERSE_SHEET, Sheets
        cols = list(sample[0].keys()) if sample else []
        Sheets().replace_tab(UNIVERSE_SHEET, "GLEIF precision", [cols + ["correct (yes/no)"]] + [[str(r[c]) for c in cols] + [""] for r in sample], raw=True)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        log.info("gleif sample: sheet not written (%s)", type(e).__name__)
    print("GLEIF", json.dumps(dict(stats)), "by region", json.dumps(dict(by_region.most_common())))
    return dict(stats)


def load_matches(path=OUT):
    out = {}
    if path.exists():
        for line in open(path, encoding="utf-8"):
            try:
                d = json.loads(line); out[d["key"]] = d
            except (ValueError, KeyError):
                pass
    return out


if __name__ == "__main__":
    import argparse
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=int, default=7); ap.add_argument("--universe"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    from pathlib import Path
    run(a.max_age_days, Path(a.universe) if a.universe else None, a.force)
    sys.exit(0)
