"""Company website for the leading US import buyers via Wikidata (free, no key). Exact-name matches only;
results cached in data/leads/enrich.json and re-checked after 60 days."""
import datetime as dt
import json
import re

from .common import LEADS, log, polite, session, today

API = "https://www.wikidata.org/w/api.php"
CACHE = LEADS / "enrich.json"
SUFFIX = re.compile(r"\b(inc|incorporated|llc|l l c|ltd|limited|corp|corporation|co|company|lp|llp|plc|sa|s a|"
                    r"de cv|s a de c v|gmbh|ag|usa|us|america|the)\b\.?", re.I)


def norm(name):
    n = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return re.sub(r"\s+", " ", SUFFIX.sub(" ", n)).strip()


def lookup(s, name):
    r = s.get(API, params={"action": "wbsearchentities", "search": name, "language": "en", "type": "item",
                           "limit": 5, "format": "json"}, timeout=30)
    hits = [h for h in r.json().get("search", []) if norm(h.get("label", "")) == norm(name)]
    if not hits:
        return ""
    r = s.get(API, params={"action": "wbgetentities", "ids": "|".join(h["id"] for h in hits),
                           "props": "claims|descriptions", "languages": "en", "format": "json"}, timeout=30)
    for qid, e in r.json().get("entities", {}).items():
        desc = (e.get("descriptions", {}).get("en", {}) or {}).get("value", "").lower()
        if any(w in desc for w in ("person", "album", "film", "song", "football", "village", "river")):
            continue
        for c in e.get("claims", {}).get("P856", []):
            v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
            if v:
                return v
    return ""


def run(companies, limit=250):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    s = session(); t = today(); n = 0
    for name in companies:
        c = cache.get(name)
        if c and (t - dt.date.fromisoformat(c["checked"])).days < 60:
            continue
        if n >= limit:
            break
        try:
            cache[name] = {"website": lookup(s, name), "checked": str(t)}
        except Exception as e:  # noqa: BLE001
            log.warning("wikidata %s: %s", name, e); continue
        n += 1; polite(0.3)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True))
    log.info("enrich: looked up %d, cached %d", n, len(cache))
    return cache
