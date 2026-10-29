"""Israel: registry of public bodies (and large companies) that publish tenders and calls for proposals.

Sources (official or open, no scraping of commercial aggregators):
  - data.gov.il: unified list of municipal authorities (Digital Israel), government companies (Ministry of Finance),
    religious councils (Ministry of Religious Services), water and sewage corporations (Water Authority datasets).
  - Wikidata / Hebrew Wikipedia API: official websites (P856) and hospitals, universities, ports, state-owned
    enterprises in Israel.
  - leads/il_curated.csv: statutory bodies, clusters, drainage authorities, HMOs, academia, infrastructure and large
    companies (names; website only where known).

Output: data/israel/bodies.csv. Discovery results (tenders_urls, status) of an existing registry are kept.
Run: python -m leads.il_registry
"""
import csv
import datetime as dt
import html
import re
import time
from pathlib import Path
import requests

from .common import DATA, log

OUT = DATA / "israel" / "bodies.csv"
CURATED = Path(__file__).with_name("il_curated.csv")
UA = "SinderTenderMonitor/1.0 (public procurement research; https://github.com/etaram/commodity-feeder)"
FIELDS = ["id", "type", "name", "name_short", "name_en", "district", "website", "website_source", "tenders_urls", "status",
          "last_discovered", "last_scanned", "open_items", "priority", "keep"]
TYPE_PRIORITY = {"city_association": 2, "planning_committee": 3, "municipality": 1, "regional_council": 1, "local_council": 1, "gov_company": 1, "infra": 1,
                 "statutory": 2, "cluster": 2, "water_corp": 2, "hmo": 2, "hospital": 2, "municipal_company": 2,
                 "drainage": 3, "academic": 3, "religious_council": 3, "company": 3}
SKIP_DOMAINS = ("wikipedia.org", "wikidata.org", "facebook.com", "youtube.com", "instagram.com", "twitter.com",
                "x.com", "linkedin.com", "google.", "cbs.gov.il", "archive.org", "waze.com", "tripadvisor")

S = requests.Session()
S.headers["User-Agent"] = UA


def _get(url, **params):
    for i in range(3):
        try:
            r = S.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503):
                time.sleep(5 * (i + 1)); continue
            return None
        except Exception:  # noqa: BLE001
            time.sleep(3)
    return None


def ckan_records(resource_id):
    out, off = [], 0
    while True:
        j = _get("https://data.gov.il/api/3/action/datastore_search", resource_id=resource_id, limit=1000, offset=off)
        if not j:
            break
        recs = j["result"]["records"]
        out += recs
        if len(recs) < 1000:
            break
        off += 1000
    return out


def ckan_find(q):
    j = _get("https://data.gov.il/api/3/action/package_search", q=q, rows=20)
    return j["result"]["results"] if j else []


def norm(name):
    s = re.sub(r'["\'״׳`]', "", name or "")
    s = re.sub(r"\b(בע\s?מ|בעמ|ltd|limited|inc)\b", "", s, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip().lower()


def clean_url(u):
    u = html.unescape(u or "").strip()
    m = re.search(r"https?://[^\s\"'”<>]+", u)
    if not m:
        m = re.search(r"(www\.[^\s\"'”<>]+)", u)
        u = "https://" + m.group(1) if m else ""
    else:
        u = m.group(0)
    u = u.rstrip("/.,”")
    return u if u and not any(d in u for d in SKIP_DOMAINS) else ""


# ---------------------------------------------------------------- Wikipedia / Wikidata websites
def wp_lookup(titles):
    """Hebrew Wikipedia titles -> {title: (qid, [extlinks])}."""
    out = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        j = _get("https://he.wikipedia.org/w/api.php", action="query", titles="|".join(chunk), redirects=1,
                 prop="pageprops|extlinks", ellimit="max", ppprop="wikibase_item", format="json", formatversion=2)
        if not j:
            continue
        q = j.get("query", {})
        back = {}
        for x in q.get("normalized", []) + q.get("redirects", []):
            back[x["to"]] = back.get(x["from"], x["from"])
        for p in q.get("pages", []):
            if p.get("missing"):
                continue
            orig = back.get(p["title"], p["title"])
            orig = back.get(orig, orig)
            out[orig] = ((p.get("pageprops") or {}).get("wikibase_item"), [e["url"] for e in p.get("extlinks", [])])
        time.sleep(0.5)
    return out


def wd_websites(qids):
    out = {}
    qids = [q for q in qids if q]
    for i in range(0, len(qids), 45):
        j = _get("https://www.wikidata.org/w/api.php", action="wbgetentities", ids="|".join(qids[i:i + 45]),
                 props="claims", format="json")
        for q, e in ((j or {}).get("entities") or {}).items():
            for c in (e.get("claims") or {}).get("P856", []):
                v = clean_url(((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", ""))
                if v:
                    out.setdefault(q, v)
        time.sleep(0.5)
    return out


def wp_search(name):
    j = _get("https://he.wikipedia.org/w/api.php", action="query", list="search", srsearch=name, srlimit=1,
             format="json", formatversion=2)
    hits = ((j or {}).get("query") or {}).get("search") or []
    return hits[0]["title"] if hits else None


def wikidata_bodies():
    """Hospitals, universities, colleges, ports, government agencies and state-owned enterprises in Israel."""
    types = {"Q16917": "hospital", "Q3918": "academic", "Q189004": "academic", "Q44782": "infra",
             "Q327333": "statutory", "Q270791": "gov_company"}
    q = ("SELECT ?o ?he ?w ?t WHERE { VALUES ?t { " + " ".join("wd:" + k for k in types) + " } "
         "?o wdt:P17 wd:Q801; wdt:P31 ?t; wdt:P856 ?w. ?o rdfs:label ?he FILTER(lang(?he)='he') }")
    j = None
    try:
        r = S.get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"}, timeout=180)
        j = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("wikidata sparql: %s", e)
    out = []
    for b in ((j or {}).get("results") or {}).get("bindings", []):
        out.append({"type": types[b["t"]["value"].split("/")[-1]], "name": b["he"]["value"],
                    "website": clean_url(b["w"]["value"]), "website_source": "wikidata"})
    return out


# ---------------------------------------------------------------- official lists
MUNI_TYPE = {"עירייה": "municipality", "מועצה מקומית": "local_council", "מועצה אזורית": "regional_council"}


def municipal():
    en = {}
    for r in ckan_records("e9701dcb-9f1c-43bb-bd44-eb380ade542f"):
        en[str(r.get("symbol_number"))] = (r.get("name_in_english") or "").strip().lower()
    out = []
    for r in ckan_records("c4916937-f5d3-4295-a22e-88a1af5cde6a"):
        t = MUNI_TYPE.get((r.get("LocalAuthorityType") or "").strip(), "local_council")
        name = (r.get("LocalAuthorityName") or "").strip()
        out.append({"type": t, "name": (r.get("LocalAuthorityLongName") or name).strip(), "name_short": name,
                    "district": r.get("LocalAuthorityDistrict") or "", "id": f"MUNI-{r.get('LocalAuthorityCode')}",
                    "name_en": en.get(str(r.get("LocalAuthorityCode")), "") if t != "regional_council" else ""})
    return out


def gov_companies():
    out = []
    for r in ckan_records("2d5abbad-4809-4900-b74f-b2f8b40bcfb8"):
        if "פירוק" in (r.get("STATUS") or ""):
            continue
        out.append({"type": "gov_company", "name": (r.get("COMPANY_NAME") or "").strip(),
                    "website": clean_url(r.get("COMPANY_SITE")), "website_source": "data.gov.il" if r.get("COMPANY_SITE") else ""})
    return out


def religious_councils():
    out = []
    for r in ckan_records("80822f1d-ad3e-437c-b799-92c57aa06477"):
        n = (r.get("Council_name") or "").strip()
        out.append({"type": "religious_council", "name": f"המועצה הדתית {n}", "name_short": n,
                    "website": clean_url(r.get("Website")), "website_source": "data.gov.il"})
    return out


def water_corps():
    names = set()
    for p in ckan_find("תאגידי מים וביוב") + ckan_find("תאגיד מים"):
        for res in p.get("resources", [])[:2]:
            if not res.get("datastore_active"):
                continue
            recs = ckan_records(res["id"])[:20000]
            if not recs:
                continue
            cols = [c for c in recs[0] if re.search(r"תאגיד|corporation|TAAGID", str(c), re.I)]
            for c in cols:
                for x in recs:
                    v = str(x.get(c) or "").strip()
                    if 3 < len(v) < 60 and not re.search(r"^\d+$|אין|לא רלוונטי", v):
                        names.add(v)
    out = [{"type": "water_corp", "name": n if n.startswith(("תאגיד", "מי ", "מי-")) or "מים" in n else f"תאגיד המים {n}"}
           for n in sorted(names)]
    log.info("water corporations: %d", len(out))
    return out


def municipal_companies():
    """Municipal economic companies: names from Hebrew Wikipedia search (official websites come from discovery)."""
    names = set()
    for q in ("החברה הכלכלית לפיתוח", "החברה הכלכלית", "חברה כלכלית", "חברה עירונית לפיתוח", "החברה העירונית",
              "החברה לפיתוח", "חברה לפיתוח", "איגוד ערים", "ועדה מרחבית לתכנון ובנייה", "ועדה מקומית לתכנון ובנייה",
              "תאגיד מים", "תאגיד המים", "החברה למשק וכלכלה", "החברה לתרבות הפנאי", "החברה העירונית לתרבות"):
        off = 0
        while off < 300:
            j = _get("https://he.wikipedia.org/w/api.php", action="query", list="search", srsearch=f'intitle:"{q}"',
                     srlimit=50, sroffset=off, format="json", formatversion=2)
            hits = ((j or {}).get("query") or {}).get("search") or []
            for h in hits:
                names.add(h["title"])
            if len(hits) < 50:
                break
            off += 50
            time.sleep(0.5)
    out = []
    for n in sorted(names):
        if re.search(r"^(רשימת|פורטל|תבנית|קטגוריה|ויקיפדיה)|ועדת ", n):
            continue
        t = ("water_corp" if re.search(r"תאגיד.*מים|מים וביוב", n) else
             "municipal_company" if re.search(r"חברה|החברה", n) else
             "city_association" if "איגוד ערים" in n else "planning_committee" if "ועדה" in n else "")
        if t:
            out.append({"type": t, "name": n})
    return out


def curated():
    return [{"type": r["type"], "name": r["name"], "website": clean_url(r.get("website")),
             "website_source": "curated" if r.get("website") else ""}
            for r in csv.DictReader(open(CURATED, encoding="utf-8"))]


def _wp_titles(b):
    n, short, t = b["name"], b.get("name_short") or "", b["type"]
    v = [n]
    if short:
        v.append(short)
        if t == "regional_council":
            v += [f"מועצה אזורית {short}"]
        if t == "local_council":
            v += [f"{short} (מועצה מקומית)"]
    v.append(re.sub(r'\s*בע["״]?מ\s*$', "", n))
    return list(dict.fromkeys(x for x in v if x))


def build():
    old = {}
    if OUT.exists():
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            old[r["id"]] = r
    bodies = []
    for fn in (municipal, gov_companies, religious_councils, water_corps, municipal_companies, curated, wikidata_bodies):
        try:
            got = fn()
            log.info("%s: %d", fn.__name__, len(got))
            bodies += got
        except Exception as e:  # noqa: BLE001
            log.warning("%s failed: %s", fn.__name__, e)
    # de-duplicate by normalised name (first source wins, later ones fill the website)
    seen, uniq = {}, []
    for b in bodies:
        k = norm(b["name"])
        if not k:
            continue
        if k in seen:
            if not seen[k].get("website") and b.get("website"):
                seen[k]["website"], seen[k]["website_source"] = b["website"], b.get("website_source", "")
            continue
        seen[k] = b
        uniq.append(b)
    # websites from Hebrew Wikipedia -> Wikidata P856 (fallback: external links on the article)
    need = [b for b in uniq if not b.get("website")]
    titles = sorted({t for b in need for t in _wp_titles(b)})
    pages = wp_lookup(titles)
    qsites = wd_websites([v[0] for v in pages.values()])
    for b in need:
        for t in _wp_titles(b):
            if t in pages:
                qid, links = pages[t]
                site = qsites.get(qid)
                if not site:
                    # an external link on the article counts only when it is a local-authority domain
                    site = next((clean_url(u) for u in links if re.search(r"\.muni\.il", u) and clean_url(u)), "")
                    site = re.sub(r"^(https?://[^/]+).*$", r"\1", site)
                    src = "wikipedia link" if site else ""
                else:
                    src = "wikidata"
                if site:
                    b["website"], b["website_source"] = site, src
                    break
    # last resort: Hebrew Wikipedia search for the name
    for b in [b for b in uniq if not b.get("website")][:400]:
        t = wp_search(b["name"])
        if t and norm(b.get("name_short") or b["name"])[:6] in norm(t):
            p = wp_lookup([t]).get(t)
            if p:
                site = wd_websites([p[0]]).get(p[0]) if p[0] else ""
                if site:
                    b["website"], b["website_source"] = site, "wikipedia search"
        time.sleep(0.3)
    rows, ids = [], set()
    for b in uniq:
        bid = b.get("id") or "IL-" + re.sub(r"\W+", "-", norm(b["name"]))[:40].strip("-")
        while bid in ids:
            bid += "x"
        ids.add(bid)
        o = old.get(bid, {})
        site = b.get("website") or o.get("website", "")
        same = o.get("website") == site
        rows.append({
            "id": bid, "type": b["type"], "name": b["name"], "name_short": b.get("name_short", ""),
            "name_en": b.get("name_en", ""), "district": b.get("district", ""), "website": site,
            "website_source": b.get("website_source") or o.get("website_source", ""),
            "tenders_urls": o.get("tenders_urls", "") if same else "", "status": o.get("status", "") if same else "",
            "last_discovered": o.get("last_discovered", "") if same else "", "last_scanned": o.get("last_scanned", ""),
            "open_items": o.get("open_items", ""), "priority": TYPE_PRIORITY.get(b["type"], 3),
            "keep": "candidate" if b["type"] == "company" else "yes",
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (int(r["priority"]), r["type"], r["name"])))
    from collections import Counter
    log.info("registry: %d bodies, %d with website; %s", len(rows), sum(1 for r in rows if r["website"]),
             dict(Counter(r["type"] for r in rows)))
    (DATA / "israel" / "registry_built.txt").write_text(dt.datetime.utcnow().isoformat(timespec="minutes"))
    return rows


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    build()
