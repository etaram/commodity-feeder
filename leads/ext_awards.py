"""Large public award datasets that feed the Supplier Universe only (kept private, not in the public award files):
  World Bank  - all contract awards in Investment Project Financing since FY2020 (~300k, every borrower country):
                goods, works and non-consulting services, supplier name and registration country
  USAspending - US federal contracts, last 24 months: every foreign supplier, and US manufacturers, wholesalers,
                farm, fishing and mining companies with awards >= USD 250k (name, UEI, address, NAICS)
Each dataset is refreshed weekly into data/private/awards_ext/<name>.jsonl (same row shape as award files)."""
import datetime as dt
import json
import time

from .common import PRIVATE, clean, log, polite, session, today
from .regions import iso3
from .sectors import classify

OUT = PRIVATE / "awards_ext"
WB = "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice"
USAS = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
WB_KEEP = {"Goods", "Works", "Non-consulting Services", "Non-Consulting Services"}


VERSION = {"usaspending": "2"}  # bump to force a refresh after the segment list changes


def _fresh(name, days=7):
    p = OUT / f"{name}.jsonl"
    v = OUT / f"{name}.v"
    if VERSION.get(name) and (not v.exists() or v.read_text().strip() != VERSION[name]):
        return False
    return p.exists() and (time.time() - p.stat().st_mtime) < days * 86400 and p.stat().st_size > 1000


def _write(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    if VERSION.get(name):
        (OUT / f"{name}.v").write_text(VERSION[name])
    with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _date(s):
    try:
        return dt.datetime.strptime(s, "%d-%b-%Y").date().isoformat()
    except (TypeError, ValueError):
        return ""


def worldbank(s, budget_end):
    rows, skip, top, total = [], 0, 5000, None
    while time.time() < budget_end:
        r = s.get(WB, params={"datasetId": "DS00005", "resourceId": "RS00005", "top": top, "skip": skip,
                              "type": "json"}, timeout=180)
        if r.status_code == 429:
            polite(40); continue
        if r.status_code != 200:
            log.warning("WB awards %s %s", r.status_code, r.text[:200]); break
        j = r.json(); total = j.get("count"); data = j.get("data") or []
        for c in data:
            if c.get("procurement_category") not in WB_KEEP:
                continue
            usd = c.get("supplier_contract_amount_usd") or 0
            name = clean(c.get("supplier"), 120)
            if usd < 50_000 or not name:
                continue
            text = clean(c.get("contract_description"), 300)
            sec, _ = classify(f"{text} {c.get('procurement_category')}")
            rows.append({"id": f"WBC-{c.get('wb_contract_number')}", "source": "World Bank awards", "sector": sec,
                         "title": text[:200], "buyer": clean(c.get("project_name"), 120),
                         "country": iso3(c.get("borrower_country_code") or "") or "", "cpv": "",
                         "published": _date(c.get("contract_signing_date")), "winners": [name],
                         "winner_country": iso3(c.get("supplier_country_code") or "") or "", "value": usd,
                         "currency": "USD", "nature": c.get("procurement_category")})
        skip += top
        if not data or (total and skip >= total):
            break
        polite(1.5)
    log.info("World Bank awards: %d kept of %s, reached %d", len(rows), total, skip)
    return rows, bool(total and skip >= total)


def _usas_segment(s, flt, budget_end, max_pages):
    rows, page = [], 1
    fields = ["Award ID", "Recipient Name", "Award Amount", "Description", "Awarding Agency", "Start Date",
              "Recipient Location", "NAICS", "Recipient UEI"]
    while page <= max_pages and time.time() < budget_end:
        body = {"filters": flt, "fields": fields, "limit": 100, "page": page, "sort": "Award Amount", "order": "desc"}
        r = s.post(USAS, json=body, timeout=120)
        if r.status_code in (429, 500, 502, 503):
            polite(10); continue
        if r.status_code != 200:
            log.warning("USAspending %s %s", r.status_code, r.text[:200]); break
        j = r.json()
        for a in j.get("results") or []:
            loc = a.get("Recipient Location") or {}
            naics = a.get("NAICS") or {}
            name = clean(a.get("Recipient Name"), 120)
            if not name:
                continue
            nd = naics.get("description") or ""
            sec, _ = classify(nd or a.get("Description") or "")
            wc = loc.get("location_country_code") or "USA"
            addr = ", ".join(x for x in [loc.get("address_line1"), loc.get("city_name"), loc.get("state_code") or
                                         loc.get("foreign_province"), loc.get("zip5") or loc.get("foreign_postal_code"),
                                         loc.get("country_name")] if x)
            rows.append({"id": f"USA-{a.get('generated_internal_id')}", "source": "USAspending", "sector": sec,
                         "title": clean(a.get("Description"), 200), "buyer": clean(a.get("Awarding Agency"), 120),
                         "country": "USA", "cpv": "", "published": (a.get("Start Date") or "")[:10],
                         "winners": [name], "winner_country": wc, "value": a.get("Award Amount") or 0,
                         "currency": "USD", "naics": f"{naics.get('code', '')} {nd}".strip(),
                         "contacts": [{"name": name, "country": wc, "legal_id": f"UEI:{a.get('Recipient UEI')}"
                                       if a.get("Recipient UEI") else "", "address": addr, "email": "", "phone": "",
                                       "website": ""}]})
        if not (j.get("page_metadata") or {}).get("hasNext"):
            break
        page += 1
        polite(0.3)
    return rows


def usaspending(s, budget_end):
    t = today()
    period = [{"start_date": str(t - dt.timedelta(days=730)), "end_date": str(t)}]
    base = {"award_type_codes": ["A", "B", "C", "D"], "time_period": period}
    segs = [("foreign", dict(base, recipient_scope="foreign", award_amounts=[{"lower_bound": 25000}]), 100)]
    for code in ["11", "21", "311", "312", "313", "314", "315", "316", "321", "322", "324", "325", "326", "327",
                 "331", "332", "333", "334", "335", "336", "337", "339", "423", "424", "425",
                 "481", "483", "484", "486", "488", "492", "493"]:
        segs.append((code, dict(base, recipient_scope="domestic", naics_codes={"require": [code]},
                                award_amounts=[{"lower_bound": 250000}]), 40))
    rows = []
    for name, flt, pages in segs:
        got = _usas_segment(s, flt, budget_end, pages)
        rows += got
        log.info("USAspending %s: %d", name, len(got))
    return rows


def fetch():
    s = session()
    stats = {}
    t_end = time.time() + 1500
    if not _fresh("worldbank"):
        rows, complete = worldbank(s, t_end - 900)
        if rows and (complete or not (OUT / "worldbank.jsonl").exists()):
            _write("worldbank", rows)
        stats["worldbank"] = len(rows)
    if not _fresh("usaspending"):
        rows = usaspending(s, t_end)
        contacts = []
        for r in rows:
            contacts += r.pop("contacts", [])
        if rows:
            _write("usaspending", rows)
            with open(PRIVATE / "contacts_usaspending.jsonl", "w", encoding="utf-8") as f:
                for c in contacts:
                    c["source"] = "USAspending"
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
        stats["usaspending"] = len(rows)
    log.info("external awards %s", stats)
    return [], stats
