"""What each company does, in English, from its own website text: open-source models and code, no paid model calls.

The company checks (leads/company_check.py, a scraper over the companies' own sites) keep each site's description
and product headings in the site's language. A Ukrainian, Polish or Thai description is not found by an English
search and tells the user nothing. This layer adds, per checked company:

  about_en   the site's description and first product headings in English (Argos Translate, open-source neural MT,
             offline inside the runner; English sites are kept as they are)
  role       manufacturer / farm or primary producer / trader or distributor / works contractor / service provider,
             by a multilingual sentence-embedding model (open-source MiniLM, ONNX on CPU) with its score; a weak score
             stays "unknown"
  activity   the two closest activity labels (sectors and traded commodities) by the same model, with scores
  tags       commodity and variety tags by the shared commodity table (dealdesk/lib/commodities.json), look-alikes
             removed ("coffee table" is not coffee)

Principles (leads/refine.py): the raw check is untouched, the result is a separate versioned file keyed by
supplier|country (data/checks/describe.jsonl.gz), a record is reused while its input text and the version are
unchanged, every run is time-boxed and resumes, commodity-related companies first. A model label is a reading of the
company's own words, never proof: the app shows it as "auto-read from its website".

  python -m leads.describe --minutes 20          one time-boxed pass
  python -m leads.describe --selftest            the code paths without downloading a model
"""
import argparse
import gzip
import hashlib
import json
import re
import time
from datetime import date
from pathlib import Path

from .common import DATA, log

VERSION = "describe-1"
DIR = DATA / "checks"
CHECKS = DIR / "company_checks.jsonl"
OUT = DATA / "describe" / "describe.jsonl.gz"   # its own folder and Actions cache (describe workflow), so it never races the checks
OLD_OUT = DIR / "describe.jsonl.gz"            # where the first run (inside company-check) wrote; read once, then left
PROGRESS = DATA / "leads" / "describe_progress.json"
TAX = Path(__file__).resolve().parent.parent / "dealdesk" / "lib" / "commodities.json"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ROLE_MIN, ROLE_LEAD, ACT_MIN = 0.30, 0.03, 0.28   # cosine thresholds: below them the reading is "unknown"

ROLES = {
    "manufacturer": "a manufacturer: a factory that produces and makes its own products",
    "producer": "a farm, plantation, cooperative, mine or mill that grows, harvests, extracts or processes raw commodities",
    "trader": "a trading company, wholesaler, distributor, importer or exporter that buys and sells goods made by others",
    "contractor": "a construction and engineering contractor that builds works and installs systems",
    "services": "a service provider: consulting, software, logistics, maintenance, training or professional services",
}
SECTOR_LABELS = {
    "Agriculture & food": "agriculture, food products and beverages", "Energy, fuels & utilities": "oil, gas, fuels and energy supply",
    "Power & electrical equipment": "electrical equipment, transformers, cables and generators", "Mining, minerals & metals": "mining, minerals, steel and metal products",
    "Chemicals & plastics": "chemicals, fertilizers, plastics and polymers", "Textiles, apparel & leather": "textiles, garments, footwear and leather",
    "Construction materials & building systems": "cement, building materials, pipes and construction products", "Building construction works": "building construction works",
    "Transport & civil infrastructure works": "roads, bridges, railways and civil infrastructure works", "Water & wastewater": "water treatment, pumps and wastewater systems",
    "Industrial & construction machinery": "industrial machinery, construction and agricultural machines", "Vehicles, rolling stock, ships & aircraft": "vehicles, trucks, ships, aircraft and their parts",
    "Defence & security": "defence, security and police equipment", "Healthcare & pharmaceuticals": "medical devices, hospital equipment and pharmaceuticals",
    "Scientific & measuring instruments": "laboratory, scientific and measuring instruments", "ICT & telecom": "computers, software, IT and telecommunications",
    "Furniture, appliances & consumer goods": "furniture, appliances and consumer goods", "Repair, maintenance & installation": "repair, maintenance and installation services",
    "Transport & logistics services": "freight, shipping, transport and logistics services", "Engineering & architecture services": "engineering design and architecture services",
    "Consulting, business & financial services": "consulting, business, legal and financial services", "Environment, waste & cleaning": "waste management, recycling, environment and cleaning",
}


def sha(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def taxonomy():
    return json.loads(TAX.read_text(encoding="utf-8"))["commodities"]


def _word(alts):
    return re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(a) for a in alts) + r")s?(?![^\W_])", re.I)


def tagger(tax=None):
    """text -> commodity and variety tags, by the shared commodity table (the same rules the app's search applies)."""
    rules = []
    for e in tax or taxonomy():
        rules.append((e["key"], _word(e["terms"]), re.compile(e["not"], re.I) if e["not"] else None,
                      [(name, _word(v["a"])) for name, v in e["varieties"].items()]))

    def tags(text):
        out = []
        for key, term, bad, varieties in rules:
            clean = bad.sub(" ", text) if bad else text
            if term.search(clean):
                out.append(key)
                out += [f"{key}:{name}" for name, rx in varieties if rx.search(clean)]
        return out[:12]
    return tags


SITE_ROLE = {"manufacturer": "manufacturer", "trader": "trader", "epc": "contractor", "service": "services", "services": "services"}
ROLE_WORDS = [
    ("producer", re.compile(r"\b(farms?|farming|plantations?|estates?|growers?|cooperatives?|co-?operative union|we grow|harvest(ed|ing)?|ginner(y|ies)|"
                            r"(rice|flour|oil|sugar|coffee|tea|cashew|cotton) (mill|mills|processor|processing|factory|washing station)|miners?|mining company|quarr(y|ies)|fisher(y|ies))\b", re.I)),
    ("manufacturer", re.compile(r"\b(manufactur\w+|we produce|producer of|production (plant|facility|line|capacity)|our (factory|plant)|factory|foundry|refinery)\b", re.I)),
    ("trader", re.compile(r"\b(trading (company|house)|traders?|wholesal\w+|distribut(or|ors|ion)|import(er|ers)? (and|&) export(er|ers)?|importers?|merchants?|reseller|dealer)\b", re.I)),
    ("contractor", re.compile(r"\b(general contractor|construction company|civil (works|engineering) contractor|epc|design and build|builders?)\b", re.I)),
    ("services", re.compile(r"\b(consult(ing|ancy|ants)|software|it services|logistics|freight forward\w+|law firm|training|advisory|maintenance services|agency)\b", re.I)),
]


def role_by_code(ck, english):
    """(role, basis): the role the site's own wording states. First the phrase the company check recorded on the site
    (a manufacturer that also trades stays a manufacturer), then the wording of the English description. Exporting is
    not trading: a grower or a factory exports too."""
    for r in ck.get("roles") or []:
        m = SITE_ROLE.get(str(r.get("role", "")).lower())
        if m in ("manufacturer", "contractor"):
            return m, f"site phrase: {str(r.get('phrase', ''))[:60]}"
    for role, rx in ROLE_WORDS:
        m = rx.search(english or "")
        if m:
            return role, f"description: {m.group(0)[:40]}"
    for r in ck.get("roles") or []:
        m = SITE_ROLE.get(str(r.get("role", "")).lower())
        if m:
            return m, f"site phrase: {str(r.get('phrase', ''))[:60]}"
    return "", ""


def own_text(ck):
    """The company's own words from a check: its description, then its first product headings."""
    desc = re.sub(r"\s+", " ", ck.get("description") or "").strip()
    prods = [re.sub(r"\s+", " ", p).strip() for p in (ck.get("products") or [])[:10] if p and len(p) < 90]
    return desc[:400], prods


def usable(ck):
    return ck.get("verdict") == "ok" and ck.get("name_match") in ("high", "partial") and bool((ck.get("description") or "").strip() or ck.get("products"))


def load_out():
    out = {}
    src = OUT if OUT.exists() else OLD_OUT
    if src.exists():
        with gzip.open(src, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line); out[d["key"]] = d
                except (ValueError, KeyError):
                    pass
    return out


def save_out(recs):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for k in sorted(recs):
            f.write(json.dumps(recs[k], ensure_ascii=False) + "\n")
    tmp.replace(OUT)


class Embedder:
    """Multilingual sentence embeddings on CPU (fastembed, ONNX). One instance per run; labels are embedded once."""
    def __init__(self):
        from fastembed import TextEmbedding
        self.m = TextEmbedding(MODEL)
        self.role_keys = list(ROLES)
        self.act_keys = list(SECTOR_LABELS) + [f"commodity: {e['key']}" for e in taxonomy()]
        act_text = list(SECTOR_LABELS.values()) + [", ".join(e["terms"][:5]) for e in taxonomy()]
        self.R = self._emb([f"The company is {v}" for v in ROLES.values()])
        self.A = self._emb([f"The company's business is {v}" for v in act_text])

    def _emb(self, texts):
        import numpy as np
        v = np.array(list(self.m.embed(texts, batch_size=64)), dtype="float32")
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)

    def read(self, texts):
        """Per text: (role, score) and the two closest activities with scores; weak readings are left empty."""
        import numpy as np
        V = self._emb(texts)
        out = []
        for r, a in zip(V @ self.R.T, V @ self.A.T):
            o = np.argsort(-r)
            role = (self.role_keys[o[0]], float(r[o[0]])) if r[o[0]] >= ROLE_MIN and r[o[0]] - r[o[1]] >= ROLE_LEAD else ("", float(r[o[0]]))
            top = [(self.act_keys[i], round(float(a[i]), 3)) for i in np.argsort(-a)[:2] if a[i] >= ACT_MIN]
            out.append((role[0], round(role[1], 3), top))
        return out


def translate_all(items, budget_sec, t0):
    """items: [(key, lang, [texts])] -> ({key: {i: english}}, keys attempted, languages with no model), by Argos,
    language by language, inside the time budget. A key that was not reached stays in the queue for the next run."""
    from .translate import _translate_batch, sane
    by = {}
    for key, lang, texts in items:
        by.setdefault(lang, []).append((key, texts))
    out, attempted, nomodel = {}, set(), set()
    for lang, rows in sorted(by.items(), key=lambda x: -len(x[1])):
        flat = [(k, i, t) for k, texts in rows for i, t in enumerate(texts)]
        for b in range(0, len(flat), 48):
            if time.time() - t0 > budget_sec:
                return out, attempted, nomodel
            chunk = flat[b:b + 48]
            try:
                res = _translate_batch(lang, [t for _, _, t in chunk])
            except Exception as e:  # noqa: BLE001
                log.warning("describe: translate %s: %s", lang, str(e)[:120]); break
            if not any(res):
                nomodel.add(lang); break  # no model for this language: its companies keep the original text
            for (k, i, src), en in zip(chunk, res):
                attempted.add(k)
                if en and sane(src, en):
                    out.setdefault(k, {})[i] = en.strip()
    return out, attempted, nomodel


def build(recs, checks, minutes=20, limit=0, embedder=None, translate=True):
    from .translate import detect
    tags, today, t0 = tagger(), date.today().isoformat(), time.time()
    todo, reused = [], 0
    for key, ck in checks.items():
        if not usable(ck):
            continue
        desc, prods = own_text(ck)
        h = sha(VERSION, desc, "; ".join(prods))
        old = recs.get(key)
        if old and old.get("hash") == h and (old.get("about_en") or old.get("lang") == "en" or old.get("mt") == "none"):
            reused += 1
            continue
        raw = f"{desc} {' '.join(prods)}"
        hot = 0 if tags(raw) else 1   # commodity-related companies first
        todo.append((hot, key, ck, desc, prods, h))
    todo.sort(key=lambda x: (x[0], x[1]))
    if limit:
        todo = todo[:limit]
    budget = minutes * 60
    done = 0
    for b in range(0, len(todo), 400):
        if time.time() - t0 > budget * 0.9:
            break
        batch = todo[b:b + 400]
        langs = {key: detect(f"{desc} {' '.join(prods)}"[:300]) for _, key, _, desc, prods, _ in batch}
        tr, tried, nomodel = {}, set(), set()
        if translate:
            items = [(key, langs[key], ([desc] if desc else []) + prods[:6]) for _, key, _, desc, prods, _ in batch if langs[key] != "en"]
            if items:
                tr, tried, nomodel = translate_all(items, budget, t0)
        reads = embedder.read([f"{desc}. {'; '.join(prods)}"[:500] for _, _, _, desc, prods, _ in batch]) if embedder else [("", 0.0, [])] * len(batch)
        for (_, key, ck, desc, prods, h), (role, rs, acts) in zip(batch, reads):
            lang = langs[key]
            if translate and lang != "en" and key not in tried and lang not in nomodel:
                continue  # not reached inside this run's time: stays in the queue
            src = ([desc] if desc else []) + prods[:6]
            if lang == "en":
                en, mt = src, "original"
            else:
                got = tr.get(key, {})
                en, mt = [got[i] for i in range(len(src)) if i in got], ("argos" if got else "none")
            about = "; ".join(dict.fromkeys(x for x in en if x))[:420]
            code_role, basis = role_by_code(ck, about)
            if code_role:   # the site's own wording outranks the model's reading
                role, rs = code_role, 1.0
            role_src = basis if code_role else ("embedding model" if role else "")
            recs[key] = {"key": key, "supplier": ck.get("supplier", ""), "country": ck.get("country", ""), "version": VERSION, "hash": h, "at": today,
                         "lang": lang, "mt": mt, "about_en": about, "role": role, "role_score": rs, "role_src": role_src, "activity": acts,
                         "tags": tags(f"{about} {desc} {' '.join(prods)}"), "source": ck.get("website", ""), "checked": ck.get("checked", "")}
            done += 1
    # records described before the wording rules: their role is re-read by code (cheap, no model, no translation)
    reread = 0
    for key, r in recs.items():
        if "role_src" in r or key not in checks:
            continue
        code_role, basis = role_by_code(checks[key], r.get("about_en", ""))
        if code_role:
            r["role"], r["role_score"], r["role_src"] = code_role, 1.0, basis
        else:
            r["role_src"] = "embedding model" if r.get("role") else ""
        reread += 1
    return {"version": VERSION, "at": today, "roles_reread": reread, "checked_sites_usable": reused + len(todo) if not limit else None, "reused": reused, "described_now": done,
            "queue_left": max(0, len(todo) - done), "seconds": round(time.time() - t0)}


def summary(recs):
    n = len(recs)
    by_lang, by_role, mt = {}, {}, {}
    for r in recs.values():
        by_lang[r.get("lang", "")] = by_lang.get(r.get("lang", ""), 0) + 1
        by_role[r.get("role") or "unknown"] = by_role.get(r.get("role") or "unknown", 0) + 1
        mt[r.get("mt", "")] = mt.get(r.get("mt", ""), 0) + 1
    src = {}
    for r in recs.values():
        k = (r.get("role_src") or "none").split(":")[0]
        src[k] = src.get(k, 0) + 1
    return {"role_basis": src, "described": n, "with_english": sum(1 for r in recs.values() if r.get("about_en")), "with_commodity_tags": sum(1 for r in recs.values() if r.get("tags")),
            "with_role": n - by_role.get("unknown", 0), "roles": by_role, "translation": mt, "languages": dict(sorted(by_lang.items(), key=lambda x: -x[1])[:12])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not CHECKS.exists():
        log.warning("describe: %s missing", CHECKS); return
    checks = {}
    for line in CHECKS.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line); checks[d["key"]] = d
        except (ValueError, KeyError):
            pass
    recs = load_out()
    try:
        emb = Embedder()
    except Exception as e:  # noqa: BLE001
        log.warning("describe: embedding model unavailable (%s): roles and activities left empty this run", str(e)[:160]); emb = None
    rep = build(recs, checks, minutes=a.minutes, limit=a.limit, embedder=emb)
    save_out(recs)
    rep.update(summary(recs))
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(rep, indent=1), encoding="utf-8")   # counts only; no company data
    print("describe:", json.dumps(rep))


def selftest():
    checks = {"A|ETH": {"key": "A|ETH", "supplier": "A", "country": "ETH", "verdict": "ok", "name_match": "high", "description": "Exporter of washed Sidamo and Yirgacheffe green coffee beans.", "products": ["Green coffee", "Sesame seeds"]},
              "B|ITA": {"key": "B|ITA", "supplier": "B", "country": "ITA", "verdict": "ok", "name_match": "high", "description": "Design coffee table and chairs for modern living rooms.", "products": []},
              "C|THA": {"key": "C|THA", "supplier": "C", "country": "THA", "verdict": "ok", "name_match": "none", "description": "Thai hom mali rice mill", "products": []}}
    recs = {}
    rep = build(recs, checks, minutes=1, embedder=None, translate=False)
    assert set(recs) == {"A|ETH", "B|ITA"}, recs.keys()                      # a site that does not name the company is not described
    assert "coffee:sidamo" in recs["A|ETH"]["tags"] and "sesame" in recs["A|ETH"]["tags"], recs["A|ETH"]["tags"]
    assert recs["B|ITA"]["tags"] == [], recs["B|ITA"]["tags"]                # "coffee table" is not coffee
    assert build(recs, checks, minutes=1, embedder=None, translate=False)["reused"] == 2   # unchanged input is reused
    print("selftest ok", rep)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    main()
