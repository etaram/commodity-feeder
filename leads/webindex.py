"""Compact search indexes for the Deal Desk web app (filters by country, sector, value, deadline ...).

  python -m leads.webindex tenders     -> data/web/tenders.json.gz   (public data: every open notice, short fields)
  python -m leads.webindex suppliers   -> data/web/suppliers.enc     (Supplier Universe, ENCRYPTED with WEB_INDEX_KEY;
                                          contact fields - e-mail, phone, address, legal id - are never included)

Encryption: AES-256-GCM, file = 12-byte nonce + ciphertext+tag, plaintext = gzip(JSON). The key lives only in the
GitHub secret and the Vercel environment (WEB_INDEX_KEY, base64 of 32 bytes), so the public repo holds no readable
supplier data.
"""
import base64
import csv
import glob
import gzip
import json
import os
import re
import sys

from .common import DATA, LEADS, PRIVATE, log

OUT = DATA / "web"


def _f(x):
    try:
        return round(float(x))
    except (TypeError, ValueError):
        return None


# Open to foreign bidders by rule: international competitive bidding, development-bank or UN procurement, global tenders
INTL = re.compile(r"^international|world bank|\(icb\)|\bicb\b|^global tender", re.I)


def tenders():
    rows = []
    for f in sorted(glob.glob(str(LEADS / "sheet" / "tenders_[0-9][0-9].csv"))):
        rows += list(csv.DictReader(open(f, encoding="utf-8")))
    gov = {}
    gv = LEADS / "governance.csv"
    if gv.exists():
        for r in csv.DictReader(open(gv, encoding="utf-8")):
            gov[r["country"]] = (r["integrity_score"], r["flag"])
    fit = {}
    fc = LEADS / "fit.csv"
    if fc.exists():
        for r in csv.DictReader(open(fc, encoding="utf-8")):
            fit[r["id"]] = r
    deal = {}
    dc = LEADS / "deal_calc.csv"
    if dc.exists():
        for r in csv.DictReader(open(dc, encoding="utf-8")):
            deal[r["id"]] = r
    out = []
    for r in rows:
        if not r.get("id"):
            continue
        d = deal.get(r["id"], {})
        acc = (r.get("access") or "").lower()
        out.append({
            "id": r["id"], "c": r.get("country", ""), "rg": r.get("region", ""), "s": r.get("sector", ""),
            "g": r.get("commodity", ""), "t": (r.get("title_en") or "")[:160], "b": (r.get("buyer") or "")[:80],
            "v": _f(r.get("est_value_usd")), "dl": r.get("deadline", ""), "dd": _f(r.get("days_left")),
            "d": r.get("decision", ""), "ev": _f(d.get("priority_ev_usd") or r.get("ev_usd")), "sc": _f(r.get("score")),
            "src": r.get("source", ""), "st": r.get("stage", ""), "l": r.get("link", ""), "n": 1 if r.get("new") else 0,
            "acc": "set-aside" if "set-aside" in acc else "intl" if INTL.search(acc) else "",
            "rt": d.get("route", "") or fit.get(r["id"], {}).get("route", ""), "fw": (fit.get(r["id"], {}).get("fit_why") or "")[:160], "ff": (fit.get(r["id"], {}).get("fit_flags") or "")[:160],
            "ig": _f(gov.get(r.get("country", ""), ("", ""))[0]), "if": gov.get(r.get("country", ""), ("", ""))[1],
        })
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode()
    (OUT / "tenders.json.gz").write_bytes(gzip.compress(raw, 9))
    log.info("web index: %d tenders, %.1f MB raw, %.1f MB gz", len(out), len(raw) / 1e6, (OUT / "tenders.json.gz").stat().st_size / 1e6)


SUP_FIELDS = {"quality": "q", "supplier": "n", "country": "c", "region": "rg", "tier": "tr", "main_sector": "s",
              "other_sectors": "s2", "type": "ty", "trader": "td", "epc": "epc", "logistics_role": "lg",
              "products": "p", "commodities": "cm", "exports": "x", "wins": "w", "won_usd_est": "u",
              "buyer_countries": "bc", "website": "web", "last_win": "lw",
              "tier_reason": "why", "shipments_12m": "sh", "hs_codes": "hs",
              # what the company actually supplied (titles of contracts it won) and its stated industry: the evidence
              # supplier research searches when the product field is empty
              "supplied": "sp", "industries": "in", "web_title": "wt",
              "employees": "em", "notable": "nt",  # size signals shown on the company card
              "founded": "fy", "size_band": "sz"}  # founding year and size band the company states (refined layer)
CUT = {"sz": 60, "why": 90, "p": 160, "hs": 30, "cm": 70, "s2": 70, "n": 90, "bc": 40, "web": 80, "sp": 200, "in": 80, "wt": 80, "hd": 140}


def _hs_names():
    """HS-4 heading descriptions (data/hs4.csv), so a supplier known only by its customs codes is found by product words."""
    try:
        return {r["hs4"]: r["description"] for r in csv.DictReader(open(DATA / "hs4.csv", encoding="utf-8"))}
    except OSError:
        return {}


def suppliers(limit=250_000):  # tiers 1-3 (about 218k); was 90k, which cut the universe
    key = os.environ.get("WEB_INDEX_KEY", "")
    if not key:  # kept in the private Supplier Universe sheet (hidden tab Config), readable by the service account
        try:
            from .push import UNIVERSE_SHEET, Sheets
            key = next((r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B5") if len(r) > 1 and r[0] == "WEB_INDEX_KEY"), "")
        except Exception as e:  # noqa: BLE001
            log.warning("web index key from sheet: %s", e)
    if not key:
        log.warning("web index suppliers: WEB_INDEX_KEY not set - skipped"); return
    src = PRIVATE / "universe.csv"
    if not src.exists():
        log.warning("web index suppliers: %s missing", src); return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    out, hsn = [], _hs_names()
    try:  # contract items in English (leads/describe_supplied.py, open-source translation); empty until it has run
        from .describe_supplied import english as _sp_en, load as _sp_load
        sp_cache = _sp_load()
    except Exception:  # noqa: BLE001
        sp_cache = {}
    for r in csv.DictReader(open(src, encoding="utf-8")):
        if len(out) >= limit:
            break
        x = {}
        for k, short in SUP_FIELDS.items():
            v = (r.get(k) or "").strip()
            if not v:
                continue
            if short == "sp" and sp_cache:
                v = _sp_en(v, sp_cache)
            if short in ("q", "w", "u", "sh"):
                v = _f(v)
                if v is None:
                    continue
            elif short in CUT:
                v = v[:CUT[short]]
            x[short] = v
        if x.get("hs") and hsn:
            d = "; ".join(dict.fromkeys(hsn[h[:4]] for h in re.split(r"[\s,;]+", x["hs"]) if h[:4] in hsn))
            if d:
                x["hd"] = d[:CUT["hd"]]
        x["qv"] = 2  # quality already scaled for service-only firms (dealdesk/lib/supfit.ts skips these rows)
        if r.get("dup_of"):  # a duplicate of another record (leads/refine.py): the canonical record is the one searched
            continue
        if r.get("refine") and "conflicts" in r["refine"]:
            x["rc"] = 1  # the refined layer found a conflict: shown as "check first", never as proof
        if r.get("website_basis"):
            x["wb"] = r["website_basis"][:80]
        if x.get("n") and x.get("tr") in ("1", "2", "3"):  # proven (tier 1-2) and qualified (tier 3); tier 4 stays out
            out.append(x)
    # Ethiopian coffee exporters with a recorded export volume (leads/eth_market.py: the Coffee and Tea Authority's export
    # record): proven by an official record, so they rank as proven suppliers; marketplace-only sellers stay a listing
    ee = LEADS / "eth_exporters.csv"
    if ee.exists():
        have = {(x.get("n", "").lower(), x.get("c", "")) for x in out}
        n_ee = 0
        for r in csv.DictReader(open(ee, encoding="utf-8")):
            if not r["supplier"] or (r["supplier"].lower(), "ETH") in have:
                continue
            have.add((r["supplier"].lower(), "ETH"))
            producer = re.search(r"farmers|coop|union|plantation|farm\b|estate|growers", r["supplier"], re.I)
            if r["kind"] == "export record":
                tons, val = float(r["tons"] or 0), float(r["value_usd"] or 0)
                out.append({"n": r["supplier"][:CUT["n"]], "c": "ETH", "rg": "Sub-Saharan Africa", "tr": "2", "s": "Agriculture & food", "ty": "producer and exporter" if producer else "exporter",
                            "p": f"Green coffee (Ethiopia): exported {tons:,.0f} t worth ${val / 1e6:,.1f}M in {r['year_ec']} E.C., average {r['avg_usd_kg']} USD/kg; rank {r['rank']} among Ethiopian coffee exporters"[:CUT["p"]],
                            "hs": "0901", "x": "exporter (official export record)", "why": f"official export record: {tons:,.0f} t of coffee in {r['year_ec']} E.C.", "qv": 2})
            else:
                out.append({"n": r["supplier"][:CUT["n"]], "c": "ETH", "rg": "Sub-Saharan Africa", "tr": "3", "s": "Agriculture & food", "ty": "exporter",
                            "p": f"Green coffee (Ethiopia), offers: {r['offers']}"[:CUT["p"]], "x": "exporter (marketplace listing)", "why": "lists coffee lots on a marketplace",
                            "ds": "Ethiopian Export Market", "du": r["source_url"], "qv": 2})
            n_ee += 1
        log.info("web index: %d Ethiopian coffee exporters (official export record and marketplace)", n_ee)
    # coffee producers, cooperatives and exporters by origin (leads/coffee_sellers.py: public marketplace seller profiles):
    # the seller's own statement, shown as a directory listing to check
    cs = LEADS / "coffee_sellers.csv"
    if cs.exists():
        from .regions import region as _region
        have = {(x.get("n", "").lower(), x.get("c", "")) for x in out}
        n_cs = 0
        for r in csv.DictReader(open(cs, encoding="utf-8")):
            if not r["supplier"] or not r["country"] or (r["supplier"].lower(), r["country"]) in have:
                continue
            have.add((r["supplier"].lower(), r["country"]))
            out.append({"n": r["supplier"][:CUT["n"]], "c": r["country"], "rg": _region(r["country"]) or "", "tr": "3", "s": "Agriculture & food",
                        "ty": "producer" if r["role"] == "producer" else "trader", "td": "" if r["role"] == "producer" else "1",
                        "p": f"Green coffee ({r['country_name']}): {r['kinds']}. {r['about']}"[:CUT["p"]], "hs": "0901", "x": "coffee seller (marketplace profile)",
                        "why": "has a seller profile on a green-coffee marketplace", "ds": "Algrano", "du": r["source_url"][:160], "qv": 2})
            n_cs += 1
        log.info("web index: %d coffee sellers from marketplace profiles", n_cs)
    # Uganda's official Coffee and Cocoa Directory (leads/uganda_directory.py): co-operatives, farms, processors and
    # exporters with their contacts; an official directory listing, to verify before relying on it
    ud = LEADS / "uganda_directory.csv"
    if ud.exists():
        have = {(x.get("n", "").lower(), x.get("c", "")) for x in out}
        n_ud = 0
        for r in csv.DictReader(open(ud, encoding="utf-8")):
            if not r["supplier"] or (r["supplier"].lower(), "UGA") in have:
                continue
            have.add((r["supplier"].lower(), "UGA"))
            grows = re.search(r"cooperative|farm|producer|primary processor|processor", r["role"])
            x = {"n": r["supplier"][:CUT["n"]], "c": "UGA", "rg": "Sub-Saharan Africa", "tr": "3", "s": "Agriculture & food", "ty": "producer" if grows else "trader",
                 "td": "" if grows else "1", "p": f"{r['product'].title()} {r['role']} (Uganda, {r['location'][:40]}): {r['description']}"[:CUT["p"]],
                 "hs": "0901" if r["product"] == "coffee" else "1801", "x": f"{r['product']} {r['role']} (official directory)", "why": "listed in Uganda's official coffee and cocoa directory",
                 "ds": "UCDA Coffee and Cocoa Directory", "du": r["source_url"][:160], "qv": 2}
            if r.get("website"):
                x["web"] = r["website"][:CUT["web"]]
            ct = "; ".join(v for v in (r.get("contact_person", ""), r.get("phone", ""), r.get("email", "")) if v)
            if ct:
                x["ct"] = ct[:160]   # the contact the directory prints for the organisation
            out.append(x)
            n_ud += 1
        log.info("web index: %d Ugandan coffee and cocoa organisations from the official directory", n_ud)
    # official exporter registries and promotion-council directories (leads/registries.py): a licence or registration
    # entry is proof of status (tier 2); a promotion-council profile is the company's own words (tier 3)
    from .regions import region as _region_of
    for rf in sorted(LEADS.glob("registry_*.csv")):
        have = {(x.get("n", "").lower(), x.get("c", "")) for x in out}
        n_rf = 0
        for r in csv.DictReader(open(rf, encoding="utf-8")):
            if not r["supplier"] or (r["supplier"].lower(), r["country"]) in have:
                continue
            have.add((r["supplier"].lower(), r["country"]))
            official = "council" not in r["source"].lower() and "promotion" not in r["source"].lower()
            grows = re.search(r"cooperative|producer|farm", r["role"])
            x = {"n": r["supplier"][:CUT["n"]], "c": r["country"], "rg": _region_of(r["country"]) or "", "tr": "2" if official else "3", "s": "Agriculture & food",
                 "ty": "producer and exporter" if grows else "exporter", "td": "" if grows else "1",
                 "p": f"{r['product'].capitalize()} ({r['country']}): {r['description']}"[:CUT["p"]] + (f" Size: {r['size']}." if r.get("size") else "") + (f" Certifications: {r['certifications']}." if r.get("certifications") else ""),
                 "hs": "1801" if "cocoa" in r["product"] else "0901" if "coffee" in r["product"] else "1006" if "rice" in r["product"] else "0802" if "pistachio" in r["product"] else "1701" if "sugar" in r["product"] else "1201" if "soybean" in r["product"] else "1511" if "palm oil" in r["product"] else "1001" if "wheat" in r["product"] else "0802" if "walnut" in r["product"] else "0805" if "citrus" in r["product"] else "0808" if "pome" in r["product"] else "0806" if "grape" in r["product"] else "", "x": f"{r['licence']} (official register)" if official else "exporter (promotion council directory)",
                 "why": r["source"][:CUT["why"]], "ds": r["source"][:40], "du": r["source_url"][:160], "qv": 2}
            ct = "; ".join(v for v in (r.get("contact_person", ""), r.get("phone", ""), r.get("email", "")) if v)
            if ct:
                x["ct"] = ct[:160]
            if r.get("website"):
                x["web"] = r["website"][:CUT["web"]]
            out.append(x)
            n_rf += 1
        log.info("web index: %d from %s", n_rf, rf.name)
    # origin exporters from trade directories (leads/origin_exporters.py): searchable, but a directory listing is the
    # company's own claim, so the app caps these at "plausible: check" and links the listing ("ds", "du")
    oe = PRIVATE / "origin_exporters.csv"
    if oe.exists():
        have = {(x.get("n", "").lower(), x.get("c", "")) for x in out}
        added = 0
        for r in csv.DictReader(open(oe, encoding="utf-8")):
            ident = (r["supplier"].lower(), r["country"])  # not "key": that name holds the encryption key
            if not r["supplier"] or ident in have:
                continue
            have.add(ident)
            ty = r.get("type", "")
            out.append({"n": r["supplier"][:CUT["n"]], "c": r["country"], "tr": "3", "s": r.get("main_sector") or "Agriculture & food",
                        "ty": "manufacturer" if re.search(r"manufactur|producer", ty) else "trader", "td": "1" if "trader" in ty or "distributor" in ty else "",
                        "p": r.get("products", "")[:CUT["p"]], "x": "exporter (directory listing)", "why": "listed in a trade directory",
                        "ds": r.get("source", "")[:40], "du": r.get("source_url", "")[:160], "qv": 2})
            added += 1
        log.info("web index: %d origin exporters from directories", added)
    raw = gzip.compress(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode(), 9)
    nonce = os.urandom(12)
    enc = nonce + AESGCM(base64.b64decode(key)).encrypt(nonce, raw, None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "suppliers.enc").write_bytes(enc)
    log.info("web index: %d suppliers, %.1f MB encrypted", len(out), len(enc) / 1e6)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    what = sys.argv[1:] or ["tenders", "suppliers"]
    if "tenders" in what:
        tenders()
    if "suppliers" in what:
        suppliers()
