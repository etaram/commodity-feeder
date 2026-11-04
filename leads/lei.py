"""Company groups from the GLEIF LEI register (free, official, 60 requests a minute).

For the companies that matter most (repeat winners, the seed list, play entities), find the LEI record whose legal
name matches and the ultimate parent. "TBEA Shenyang Transformer" and "TBEA Deyang Cable" then fold into one group,
TBEA Co., Ltd., with one relationship history. Cache in data/leads/lei_cache.json (committed), LOOKUPS_PER_RUN new
names per run so a run stays under five minutes; the cache fills over a few days.
Output: data/leads/groups_lei.csv (company, country, lei, legal_name, parent_lei, parent_name, parent_country).
Run inside leads.run: python -m leads.lei
"""
import csv
import json
import re
import time

from .common import LEADS, log, session, today

API = "https://api.gleif.org/api/v1/lei-records"
CACHE = LEADS / "lei_cache.json"
LOOKUPS_PER_RUN = 250
NOISE = re.compile(r"\b(ltd|limited|inc|co|corp|corporation|company|plc|sa|ag|gmbh|llc|spa|srl|bv|nv|as|ab|oy|pty|pvt|private|public|joint stock|jsc|pjsc|llp|s\.?a\.?|s\.?p\.?a\.?)\b\.?", re.I)


def _norm(n):
    return re.sub(r"\s+", " ", NOISE.sub(" ", re.sub(r"[^\w\s]", " ", (n or "").lower()))).strip()


def _get(s, url, params=None):
    for i in range(3):
        try:
            r = s.get(url, params=params, timeout=40, headers={"Accept": "application/vnd.api+json"})
            if r.status_code == 429:
                time.sleep(5 * (i + 1)); continue
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return None


def lookup(s, name, country):
    """Best LEI record for a name (same country when known): legal name tokens must overlap by at least 80%."""
    want = set(_norm(name).split())
    if not want:
        return None
    j = _get(s, API, {"filter[fulltext]": name[:100], "page[size]": 10})
    best, score = None, 0.0
    for rec in (j or {}).get("data") or []:
        a = rec.get("attributes") or {}
        ent = a.get("entity") or {}
        legal = (ent.get("legalName") or {}).get("name") or ""
        got = set(_norm(legal).split())
        ov = len(want & got) / max(1, len(want | got))
        c3 = ((ent.get("legalAddress") or {}).get("country") or "")
        if country and c3 and _iso2(country) and c3 != _iso2(country):
            ov -= 0.3
        if ov > score:
            best, score = (rec.get("id"), legal, c3), ov
    if not best or score < 0.6:
        return {"lei": "", "legal_name": "", "lei_country": "", "parent_lei": "", "parent_name": "", "parent_country": "", "checked": str(today())}
    lei, legal, c3 = best
    out = {"lei": lei, "legal_name": legal[:120], "lei_country": c3, "parent_lei": "", "parent_name": "", "parent_country": "", "checked": str(today())}
    p = _get(s, f"{API}/{lei}/ultimate-parent")
    pd = (p or {}).get("data") or {}
    if pd:
        pe = ((pd.get("attributes") or {}).get("entity") or {})
        out.update({"parent_lei": pd.get("id") or "", "parent_name": ((pe.get("legalName") or {}).get("name") or "")[:120],
                    "parent_country": ((pe.get("legalAddress") or {}).get("country") or "")})
    return out


_ISO2 = {}


def _iso2(iso3):
    if not _ISO2:
        try:
            import pycountry
            for c in pycountry.countries:
                _ISO2[c.alpha_3] = c.alpha_2
        except Exception:  # noqa: BLE001
            pass
    return _ISO2.get(iso3, "")


def targets():
    """Names worth a lookup: repeat winners by value, then play entities, then the seed list."""
    out = []
    p = LEADS / "competitors.csv"
    if p.exists():
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        rows.sort(key=lambda r: -float(r.get("won_usd_est") or 0))
        out += [(r["supplier"], r.get("supplier_country") or "") for r in rows[:1500]]
    p = LEADS / "plays.csv"
    if p.exists():
        out += [(r["entity"], r.get("country") or "") for r in csv.DictReader(open(p, encoding="utf-8")) if r.get("entity_kind") in ("winner", "buyer")]
    seen, uniq = set(), []
    for n, c in out:
        k = _norm(n)
        if k and k not in seen:
            seen.add(k); uniq.append((n, c))
    return uniq


def build():
    s = session()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    done = 0
    for name, country in targets():
        k = _norm(name)
        if k in cache or done >= LOOKUPS_PER_RUN:
            continue
        r = lookup(s, name, country)
        if r is None:
            continue
        cache[k] = {"name": name, "country": country, **r}
        done += 1
        time.sleep(1.1)  # two calls per lookup, under 60 a minute
    CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    rows = [{"company": v["name"], "country": v["country"], "lei": v["lei"], "legal_name": v["legal_name"], "parent_lei": v["parent_lei"],
             "parent_name": v["parent_name"], "parent_country": v["parent_country"]} for v in cache.values() if v.get("lei")]
    with open(LEADS / "groups_lei.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company", "country", "lei", "legal_name", "parent_lei", "parent_name", "parent_country"]); w.writeheader(); w.writerows(rows)
    log.info("lei: %d new lookups, %d cached, %d with an LEI, %d with a parent", done, len(cache), len(rows), sum(1 for r in rows if r["parent_lei"]))
    return rows


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    for r in build()[:10]:
        print(r)
