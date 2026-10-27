"""US import buyers and their foreign suppliers per HS heading, from ImportYeti public HS pages
(US Customs bills of lading). Rotates through the tracker's HS-4 headings, a slice per run, gently."""
import datetime as dt
import html
import json
import re

from .common import LEADS, cffi_get, clean, log, master_rows, polite, today

BASE = "https://www.importyeti.com"
CACHE = LEADS / "importyeti"
STATE = LEADS / "importyeti_state.json"
PER_RUN = 60
REFRESH_DAYS = 14
FORWARDER = re.compile(r"\b(logistic|shipping|freight|forward|cargo|express|lines?|transport|customs|broker|"
                       r"container|maritime|carrier|consolidat|courier|moving|movers|dachser|kuehne|dhl|schenker|"
                       r"expeditors|ceva|panalpina|agility|nippon express|translink)\w*", re.I)


def parse(page):
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    title = clean(html.unescape(m.group(1))).split(" -- ")[0] if m else ""
    tot = re.search(r"Total Sea Shipments\s*(?:<[^>]+>\s*)*([\d,]+)", page)
    u = page.replace('\\"', '"').replace("\\\\", "\\")
    dec, recs = json.JSONDecoder(), {}
    for mm in re.finditer(r'\{"shipments_12m"', u):
        try:
            o, _ = dec.raw_decode(u, mm.start())
        except ValueError:
            continue
        url = o.get("url") or ""
        if not url.startswith(("/company/", "/supplier/")):
            continue
        key = url
        if key in recs and (recs[key].get("total_shipments") or 0) >= (o.get("total_shipments") or 0):
            continue
        recs[key] = o
    out = []
    for url, o in recs.items():
        name = clean(o.get("vendor_name"))
        out.append({
            "role": "importer" if url.startswith("/company/") else "supplier",
            "company": name, "country": o.get("country_code") or "",
            "address": clean(o.get("vendor_address"), 120),
            "shipments_12m": o.get("shipments_12m") or 0, "total_shipments": o.get("total_shipments") or 0,
            "weight_t": round((o.get("total_weight") or 0) / 1000), "teu": o.get("total_teus") or 0,
            "hs_codes": " ".join((o.get("hs_codes") or [])[:6]),
            "products": clean(o.get("product_descriptions"), 160),
            "flags": ",".join(k for k, f in (("top", "is_top_filter"), ("fast-growing", "is_fastest_growing_filter"),
                                             ("new", "is_new_filter")) if o.get(f)),
            "forwarder": "yes" if FORWARDER.search(name) else "",
            "profile": BASE + url,
        })
    return {"title": title, "total_shipments": tot.group(1) if tot else "", "records": out}


def headings():
    seen = []
    for r in master_rows():
        h = (r["hs6"] or "")[:4]
        if len(h) == 4 and h.isdigit() and h not in seen:
            seen.append(h)
    return seen


def fetch(per_run=PER_RUN):
    CACHE.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    t = today()
    due = [h for h in headings() if not state.get(h) or
           (t - dt.date.fromisoformat(state[h])).days >= REFRESH_DAYS]
    due.sort(key=lambda h: state.get(h, ""))
    done, fails = 0, 0
    for h in due[:per_run]:
        try:
            r = cffi_get(f"{BASE}/hs-codes/{h}")
        except Exception as e:  # noqa: BLE001
            log.warning("IY %s: %s", h, e); fails += 1; r = None
        if r is not None and r.status_code == 200:
            p = parse(r.text)
            if p["records"]:
                p["hs4"], p["scanned"] = h, str(t)
                (CACHE / f"{h}.json").write_text(json.dumps(p, ensure_ascii=False))
                done += 1; fails = 0
            state[h] = str(t)
        else:
            fails += 1
            log.warning("IY %s: HTTP %s", h, getattr(r, "status_code", "ERR"))
        if fails >= 4:
            log.warning("IY: stopping after repeated failures (rate limit)"); break
        polite(3)
    STATE.write_text(json.dumps(state, indent=0, sort_keys=True))
    log.info("ImportYeti headings scanned: %d (due %d)", done, len(due))
    return [], {"scanned": done, "due": len(due)}
