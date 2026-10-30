"""Supplier Universe (A-tier): every company that won a public tender in the last 24 months, across all award
sources, with what it won, where, for whom, and the contact details published in the notices.
Output is private: data/private/universe.csv (git-ignored), pushed to the private Supplier Universe sheet."""
import csv
import json
import re
from collections import defaultdict

from .common import AWARDS, LEADS, PRIVATE, log, today
from .regions import iso3, region
from .sectors import SECTORS, classify
from .taxonomy import BY_ID, group_of_text

LEGAL = re.compile(r"\b(gmbh|ag|kg|sa|s\.a\.|sas|sarl|srl|s\.r\.l\.|spa|s\.p\.a\.|bv|nv|ltd|limited|llc|inc|plc|oy|ab|as|a/s|"
                   r"sp\. z o\.o\.|s\.r\.o\.|kft|d\.o\.o\.|ooo|tov|co\.?|corp|corporation|company|group|holding)\b")
GOODS = {"AGRI_FOOD", "ENERGY", "POWER", "MINING_METALS", "CHEMICALS", "TEXTILES", "CONSTR_MAT", "MACHINERY",
         "TRANSPORT_EQ", "DEFENCE", "HEALTH", "LAB", "ICT", "CONSUMER", "WATER"}
WORKS = {"BUILDING", "INFRA", "WATER", "ENGINEERING"}
NAME2ID = {v: k for k, v in SECTORS.items()}


def norm(n):
    n = re.sub(r"[^\w ]", " ", (n or "").lower())
    n = LEGAL.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()[:80]


def _rates():
    try:
        from .run import _rates as r
        return r()
    except Exception:  # noqa: BLE001
        return {"USD": 1, "EUR": 1.08, "GBP": 1.27}


_GCACHE = {}


def _group(title):
    k = title[:160]
    if k not in _GCACHE:
        if len(_GCACHE) > 400_000:
            _GCACHE.clear()
        _GCACHE[k] = group_of_text(k)
    return _GCACHE[k]


def _item(title):
    parts = (title or "").split(" – ")
    if len(parts) >= 3:  # TED: "Country – CPV category – title" -> the English category
        title = parts[1]
    t = re.sub(r"\s+", " ", re.sub(r"^(supply|supplies|provision|procurement|purchase|acquisition|adquisici[oó]n|"
                                   r"suministro|fornecimento|aquisi[cç][aã]o|fourniture|achat|lieferung) (of|de|du|des|"
                                   r"von)?\s*", "", (title or "").strip(), flags=re.I)).strip(" .,-:;")
    return t[:70] if len(t) >= 4 else ""


def _web_profiles():
    out = {}
    p = PRIVATE / "web_profiles.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            out[d.get("key")] = d
    return out


ROLES = [("Shipping line / shipowner", r"shipping|naviera|armador|maritime|ocean|sea transport|water transport|"
                                       r"vessel|tanker|bulk carrier|chartering|ship ?owner|marine transport|deep sea|lines?\b"),
         ("Port / terminal operator", r"\bports?\b|terminal|stevedor|harbou?r|puerto|porto\b"),
         ("Freight forwarder / customs broker", r"forward|nvocc|customs|transitaire|despachante|agente de carga|"
                                                r"freight services|cargo services|clearing|transportation arrangement"),
         ("Air cargo", r"air cargo|air freight|airline|aviation|481"),
         ("Trucking / road freight", r"truck|trucking|road transport|road freight|haulage|transporte de carga|484"),
         ("Rail freight", r"rail"),
         ("Warehousing / cold storage", r"warehous|storage|cold chain|almacen|armaz|493"),
         ("Courier / express", r"courier|express|parcel|postal|492"),
         ("Shipbuilding / ship repair", r"shipbuild|shipyard|ship repair|astillero|estaleiro|336611"),
         ("Logistics / 3PL", r"logistic|log[ií]stic|supply chain|3pl|transport")]
ROLES = [(n, re.compile(rx, re.I)) for n, rx in ROLES]


def logistics_role(text):
    for n, rx in ROLES:
        if rx.search(text):
            return n
    return ""


FREE_MAIL = re.compile(r"@(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|ukr|i\.ua|meta\.ua|bigmir|"
                       r"web\.de|orange|free|laposte|wanadoo|libero|terra|uol|bol|ig|rediffmail|qq|163|126|sina|naver|"
                       r"hanmail|proton|zoho|seznam|wp\.pl|o2|interia|abv|btinternet|sky|comcast|verizon|att|"
                       r"sbcglobal|prodigy|telkomsa|mweb|iafrica|vodamail)\b", re.I)


def _research_rows():
    """Suppliers the panel worker found and verified on the web (Supplier Universe tab 'Research Suppliers')."""
    try:
        from .push import UNIVERSE_SHEET, Sheets
        v = Sheets()._req("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{UNIVERSE_SHEET}/values/'Research Suppliers'!A1:L5000")
    except BaseException as e:  # noqa: BLE001  (no credentials locally, or the tab is missing)
        log.info("research suppliers not read: %s", str(e)[:120])
        return []
    vals = v.get("values") or []
    if len(vals) < 2:
        return []
    h = [x.strip() for x in vals[0]]
    rows = [dict(zip(h, r)) for r in vals[1:]]
    return [r for r in rows if r.get("supplier")]


def epc_class(x):
    """EPC / major works contractor: most of its public contracts are works, with a large volume or one large contract.
    'international' when it won works for buyers outside its home country."""
    if x.get("industries") and re.search(r"construction|engineering|epc|contract", str(x.get("industries")), re.I) and x.get("notable"):
        return "EPC / contractor"
    if x["works"] < max(1, x["wins"] / 2) or (x["works_usd"] < 20e6 and x["ex_usd"] < 10e6):
        return ""
    home = max(x["country"].items(), key=lambda y: y[1])[0] if x["country"] else ""
    intl = any(c and home and c != home for c in x["buyer_c"])
    return "International EPC" if intl else "EPC / major contractor"


def quality(r):
    """0-100: how strong a supplier looks from public evidence (value won, repeat wins, distinct buyers, exports,
    international lenders / foreign governments as buyers, notability)."""
    import math
    q = min(35, 5 * math.log10(1 + max(0, r["won_usd_est"])) - 10) if r["won_usd_est"] else 0
    q += min(20, 6 * math.log2(1 + r["wins"])) + min(15, 4 * math.log2(1 + r["buyers"]))
    q += 10 if r["exports"] else 0
    q += 8 if any(x in r["sources"] for x in ("World Bank", "USAspending", "UNGM", "UNDP", "AIIB", "EBRD")) else 0
    q += 12 if r["notable"] else 0
    q += 15 if "Research" in r["sources"] else (8 if "Wikidata products" in r["sources"] else 0)
    q += 5 if (r["email"] or r["phone"] or r["website"]) else 0
    return round(max(0, min(100, q)))


def balance_regions(rows):
    """Within each tier, interleave regions (best of Europe, best of Latin America, best of Africa, best of South Asia...)
    so the top of the list is not dominated by EU suppliers, whose public awards are larger and better documented.
    Rows of unknown region come later. Input must already be sorted by tier then quality."""
    import collections
    seen = collections.Counter()
    keyed = []
    for i, r in enumerate(rows):
        reg = r.get("region") or "unknown"
        seen[(r["tier"], reg)] += 1
        rr = seen[(r["tier"], reg)] * (4 if reg in ("unknown", "Other") else 1)
        keyed.append(((r["tier"], rr, i), r))
    return [r for _, r in sorted(keyed, key=lambda x: x[0])]


TIER_NAMES = {"1": "Strategic", "2": "Proven", "3": "Qualified", "4": "Unproven"}


def supplier_tier(r):
    """Supplier tier 1-4 from public evidence of capacity and reach (independent of any single tender):
    1 Strategic - large and repeat public contracts (>= $10M won and 5+ wins, or >= $5M with cross-border sales),
                  or a notable producer that also wins public contracts
    2 Proven    - >= $1M won with 3+ wins, cross-border sales, or a notable producer / verified exporter
    3 Qualified - repeat winner (2+ wins) or >= $250K won, and reachable (contact or website)
    4 Unproven  - a single small award or thin data
    Returns (tier, reason)."""
    usd, wins, cross = r["won_usd_est"] or 0, r["wins"] or 0, bool(r["exports"])
    notable = bool(r["notable"]) or "Wikidata products" in r["sources"]
    reach = bool(r["email"] or r["phone"] or r["website"])
    m = f"${usd / 1e6:.1f}M won, {wins} wins" if usd >= 1e6 else f"${usd / 1e3:.0f}K won, {wins} wins"
    if (usd >= 10e6 and wins >= 5) or (usd >= 5e6 and cross) or (notable and wins >= 3 and usd >= 1e6):
        return "1", f"Strategic: {m}" + (", sells abroad" if cross else "") + (", notable producer" if notable else "")
    if (usd >= 1e6 and wins >= 3) or cross or notable:
        return "2", f"Proven: {m}" + (", sells abroad" if cross else "") + (", notable producer" if notable else "")
    if (wins >= 2 or usd >= 250e3) and reach:
        return "3", f"Qualified: {m}, reachable"
    return "4", f"Unproven: {m}" + ("" if reach else ", no contact yet")


def _awards():
    """(file, award row) from the public award files and the private external award datasets."""
    for f in sorted(AWARDS.glob("*.json")) + sorted(AWARDS.glob("*/*.json")):
        for a in json.loads(f.read_text()):
            yield f, a
    for f in sorted((PRIVATE / "awards_ext").glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    yield f, json.loads(line)
                except ValueError:
                    continue


def build():
    rates = _rates()
    sup = defaultdict(lambda: {"names": defaultdict(int), "country": defaultdict(int), "wins": 0, "usd": 0.0,
                               "sectors": defaultdict(int), "cpv": defaultdict(int), "buyer_c": set(), "buyers": set(),
                               "last": "", "first": "9999", "sources": set(), "example": "", "ex_usd": 0,
                               "email": "", "phone": "", "website": "", "address": "", "legal_id": "", "goods": 0, "works": 0,
                               "works_usd": 0.0,
                               "groups": defaultdict(int), "items": {}})
    n_aw = 0
    for f, a in _awards():
        if True:
            if a.get("empty") or not a.get("winners"):
                continue
            n_aw += 1
            wcs = [x.strip() for x in (a.get("winner_country") or "").split(",") if x.strip()]
            v, c = a.get("value"), a.get("currency")
            usd = v * rates.get(c, 0) if isinstance(v, (int, float)) and c in rates else 0
            usd = usd if 0 < usd < 2e9 else 0
            share = usd / max(1, len(a["winners"]))
            for i, w in enumerate(a["winners"]):
                k = norm(w)
                if len(k) < 3:
                    continue
                wc = iso3(wcs[i] if i < len(wcs) else (wcs[0] if wcs else "")) or ""
                x = sup[(k, wc)]
                x["names"][w] += 1; x["country"][wc] += 1; x["wins"] += 1; x["usd"] += share
                sec = a.get("sector") or NAME2ID.get(a.get("sector_name", ""), "")
                if sec:
                    x["sectors"][sec] += 1
                    x["goods"] += 1 if sec in GOODS else 0
                if sec in WORKS or str(a.get("nature", "")).lower().startswith("works"):
                    x["works"] += 1; x["works_usd"] += share
                g = a.get("group") or _group(a.get("title") or "")
                if g:
                    x["groups"][g] += 1
                if a.get("naics"):
                    x["naics"] = a["naics"]
                it = _item(a.get("title") or "")
                if it and (it in x["items"] or len(x["items"]) < 8):
                    x["items"][it] = x["items"].get(it, 0) + 1
                for cp in (a.get("cpv") or "").split()[:1]:
                    x["cpv"][cp[:8]] += 1
                x["buyer_c"].add((a.get("country") or "").split(",")[0]); x["buyers"].add(norm(a.get("buyer")))
                p = a.get("published") or ""
                x["last"] = max(x["last"], p); x["first"] = min(x["first"], p or "9999")
                x["sources"].add(a.get("source") or f.parent.name)
                if share >= x["ex_usd"]:
                    x["ex_usd"] = share; x["example"] = f"{a.get('title', '')[:120]} ({a.get('buyer', '')[:60]}, {p})"
    # contacts captured from notices (private cache)
    n_ct = 0
    for f in PRIVATE.glob("contacts_*.jsonl"):
        uniq = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            uniq[(c.get("name"), c.get("email"), c.get("phone"), c.get("legal_id"))] = c
        f.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in uniq.values()), encoding="utf-8")
        for c in uniq.values():
            k = (norm(c.get("name")), iso3(c.get("country") or "") or "")
            x = sup.get(k) or next((sup[kk] for kk in ((k[0], ""),) if kk in sup), None)
            if not x:
                continue
            n_ct += 1
            for fld in ("email", "phone", "website", "address", "legal_id"):
                if c.get(fld) and not x[fld]:
                    x[fld] = c[fld]
    # tier B: notable producers and traders (Wikidata), merged with award winners when the name matches
    notable = {}
    for f in (LEADS / "companies" / "wikidata").glob("[A-Z][A-Z][A-Z].json"):
        d = json.loads(f.read_text())
        for c in d.get("companies", []):
            notable[(norm(c["name"]), d["country"])] = c
    n_b = 0
    for k, c in notable.items():
        x = sup.get(k)
        if x is None:
            x = sup[k]; x["names"][c["name"]] += 1; x["country"][k[1]] += 1; x["tier_b"] = True; n_b += 1
            if c.get("sector"):
                x["sectors"][c["sector"]] += 1
                x["goods"] += 1 if c["sector"] in GOODS else 0
            x["sources"].add("Wikidata")
        x["website"] = x["website"] or c.get("website", "")
        x["industries"] = c.get("industries", ""); x["employees"] = c.get("employees", "")
        x["products"] = c.get("products", "")
        x["trader"] = c.get("trader", False); x["notable"] = True
    # commodity producers by product (Wikidata) and suppliers found by the panel's research worker
    n_p = n_r = 0
    pf = LEADS / "companies" / "products.json"
    extra = []
    if pf.exists():
        for c in json.loads(pf.read_text()).get("companies", []):
            extra.append(("Wikidata products", c["name"], c.get("country", ""), {
                "products": ", ".join(c.get("products", [])), "website": c.get("website", ""),
                "industries": "; ".join(c.get("industries", []))}))
    for c in _research_rows():
        extra.append(("Research", c["supplier"], c["country"], c))
    for src, name, ctry, c in extra:
        k = (norm(name), iso3(ctry) or "")
        if len(k[0]) < 3:
            continue
        x = sup.get(k)
        if x is None:
            x = sup[k]; x["names"][name] += 1; x["country"][k[1]] += 1; x["tier_b"] = True
            sec = classify(f"{c.get('products', '')} {c.get('industries', '')}")[0]
            if sec:
                x["sectors"][sec] += 1; x["goods"] += 1 if sec in GOODS else 0
        n_p += src != "Research"; n_r += src == "Research"
        x["sources"].add(src); x["notable"] = True
        prods = ", ".join(p for p in [x.get("products", ""), c.get("products", "")] if p)
        x["products"] = ", ".join(dict.fromkeys(p.strip() for p in prods.split(",") if p.strip()))[:300]
        for f_ in ("website", "email", "phone", "address"):
            if c.get(f_) and not x[f_]:
                x[f_] = c[f_]
        if c.get("industries") and not x.get("industries"):
            x["industries"] = c["industries"]
        if c.get("type") == "trader":
            x["trader"] = True
    web = _web_profiles()
    out = []
    for (k, wc), x in sup.items():
        name = max(x["names"].items(), key=lambda y: y[1])[0]
        wp = web.get(f"{name[:120]}|{wc}") or {}
        site_src = "registry/notice" if x["website"] else ""
        if not x["website"] and wp.get("website"):
            x["website"] = wp["website"]; site_src = "found (name verified)" if wp.get("discovered") else "e-mail domain"
        elif not x["website"] and x["email"] and "@" in x["email"] and not FREE_MAIL.search(x["email"]):
            x["website"] = "http://" + x["email"].split(";")[0].strip().split("@")[1] + "/"; site_src = "e-mail domain"
        if not x["email"] and wp.get("email"):
            x["email"] = wp["email"]
        if not x["phone"] and wp.get("phone"):
            x["phone"] = wp["phone"]
        about = x.get("products") or wp.get("about") or ""
        items = "; ".join(i for i, _ in sorted(x["items"].items(), key=lambda y: -y[1])[:3])
        secs = sorted(x["sectors"].items(), key=lambda y: -y[1])
        out.append({
            "supplier": name[:120], "country": wc, "region": region(wc) if wc else "",
            "tier": "", "notable": "yes" if x.get("notable") else "",
            "trader": "yes" if x.get("trader") else "", "industries": x.get("industries", ""),
            "employees": x.get("employees", ""),
            "wins": x["wins"], "won_usd_est": round(x["usd"]),
            "main_sector": SECTORS.get(secs[0][0], "") if secs else "",
            "other_sectors": "; ".join(SECTORS.get(s, s) for s, _ in secs[1:3]),
            "epc": epc_class(x),
            "type": "goods supplier" if x["goods"] >= max(1, x["wins"] / 2) else ("trader" if x.get("trader") else "works/services"),
            "logistics_role": logistics_role(f"{name} {x.get('industries', '')} {about} {items} {x.get('naics', '')}")
            if any(s_ in ("LOGISTICS", "PORTS") for s_, _ in secs[:1]) or "shipbuild" in name.lower() else "",
            "products": about[:300], "web_title": (wp.get("title") or "")[:120], "supplied": items[:240],
            "commodities": "; ".join(BY_ID[g]["name"] for g, _ in sorted(x["groups"].items(), key=lambda y: -y[1])[:3]
                                     if g in BY_ID),
            "main_cpv": max(x["cpv"].items(), key=lambda y: y[1])[0] if x["cpv"] else "",
            "buyer_countries": " ".join(sorted(c for c in x["buyer_c"] if c))[:80], "buyers": len(x["buyers"]),
            # cross-border evidence: won tenders abroad, verified by the research worker, or a known producer
            "exports": ("won abroad" if any(c and wc and c != wc for c in x["buyer_c"]) else
                        "verified (research)" if "Research" in x["sources"] else
                        "producer (Wikidata)" if "Wikidata products" in x["sources"] else ""),
            "first_win": x["first"] if x["first"] != "9999" else "", "last_win": x["last"],
            "email": x["email"], "phone": x["phone"], "website": x["website"], "website_source": site_src, "address": x["address"],
            "legal_id": x["legal_id"], "sources": "; ".join(sorted(x["sources"])), "example_award": x["example"],
            "tier_reason": "", "origin": "B" if x.get("tier_b") else "A",  # new columns stay at the end (sheet formulas)
        })
    for r in out:
        r["quality"] = quality(r)
        r["tier"], r["tier_reason"] = supplier_tier(r)
    out.sort(key=lambda r: (r["tier"], -r["quality"], -r["won_usd_est"]))  # best tier first, then quality
    out = balance_regions(out)
    out = [{"quality": r.pop("quality"), **r} for r in out]
    PRIVATE.mkdir(parents=True, exist_ok=True)
    cols = list(out[0].keys()) if out else ["supplier"]
    with open(PRIVATE / "universe.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    stats = {"awards": n_aw, "suppliers": len(out), "with_email": sum(1 for r in out if r["email"]),
             "with_phone": sum(1 for r in out if r["phone"]), "exporters": sum(1 for r in out if r["exports"]),
             "goods": sum(1 for r in out if r["type"] == "goods supplier"), "contacts_matched": n_ct,
             "tier_A": sum(1 for r in out if r["origin"] == "A"), "tier_B_notable": n_b,
             **{f"tier_{t}_{n.lower()}": sum(1 for r in out if r["tier"] == t) for t, n in TIER_NAMES.items()},
             "with_website": sum(1 for r in out if r["website"]),
             "quality_40_plus": sum(1 for r in out if r["quality"] >= 40),
             "with_any_contact": sum(1 for r in out if r["email"] or r["phone"] or r["website"] or r["address"])}
    by_region = defaultdict(int)
    for r in out:
        by_region[r["region"] or "unknown"] += 1
    stats.update({f"region: {k}": v for k, v in sorted(by_region.items(), key=lambda y: -y[1])})
    log.info("universe %s", stats)
    (PRIVATE / "universe_stats.json").write_text(json.dumps(stats))
    return out, stats


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    build()
