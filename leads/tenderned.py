"""Netherlands: national (non-European) tender notices from TenderNed, the government's procurement platform, through
its public publications API (tenderned.nl/papi/tenderned-rs-tns/v2/publicaties, newest first): tender name, buyer,
contract type, procedure, closing date, description, link to the official notice.

Only notices marked europees=false are read: those below the EU thresholds, which TED does not carry (European
notices already reach us through TED). Access (checked 2026-11-14): public JSON, no key; robots.txt does not restrict
/papi. Read politely, 1 s between pages. OPEN = published, not ended early, closing date today or later."""
import datetime as dt
import re
import time

from .common import clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

API = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
SIZE = 100
BACK_DAYS = 120
MAX_PAGES = 400
NATURE = {"D": "services", "L": "goods", "W": "works"}
AWARD = re.compile(r"gun|award|resultaat", re.I)
BUDGET = re.compile(r"(?:€|EUR)\s?([\d.]{5,})(?:,\d{2})?(?!\s*(?:per|p\.?\s?j))", re.I)


def parse(items, fetched, t):
    rows = []
    for x in items:
        dl = (x.get("sluitingsDatum") or "")[:10]
        tp = (x.get("typePublicatie") or {})
        if x.get("europees") or not dl or dl < t or x.get("isVroegtijdigeBeeindiging") or \
                (x.get("publicatiestatus") or {}).get("code") not in (None, "PUB") or AWARD.search(tp.get("omschrijving") or ""):
            continue
        name = clean(x.get("aanbestedingNaam") or "")
        if not name:
            continue
        desc = clean(x.get("opdrachtBeschrijving") or "")
        b = BUDGET.search(desc)
        val = int(b.group(1).replace(".", "")) if b else ""
        sector, how = classify(name + " " + desc[:300])
        kenmerk = str(x.get("kenmerk") or x.get("publicatieId"))
        rows.append({"id": f"NL-TN-{kenmerk}", "source": "TenderNed (Netherlands, national)", "group": "", "sector": sector,
                     "nature": NATURE.get((x.get("typeOpdracht") or {}).get("code") or "", ""), "cpv": "",
                     "classification": how, "country": "NLD", "buyer": clean(x.get("opdrachtgeverNaam") or "")[:120],
                     "title": name[:300],
                     "notice_type": f"{tp.get('omschrijving') or 'Aankondiging'} | {(x.get('procedure') or {}).get('omschrijving') or ''} (national, below EU threshold)",
                     "stage": "tender", "access": "Dutch public procurement (EU firms may bid; Dutch-language documents)",
                     "published": x.get("publicatieDatum") or "", "deadline": dl, "deadline_basis": "submission",
                     "deadline_time": (x.get("sluitingsDatum") or "")[11:16] + " CET",
                     "value": val, "currency": "EUR" if val else "",
                     "link": ((x.get("link") or {}).get("href")) or f"https://www.tenderned.nl/aankondigingen/overzicht/{x.get('publicatieId')}",
                     "source_url": API, "fetched": fetched, "contact": "", "lang": "nl", "_pub": x.get("publicatieDatum") or ""})
    return rows


def fetch():
    s, t = session(), today()
    ts, stop = str(t), str(t - dt.timedelta(days=BACK_DAYS))
    out, pages, oldest = [], 0, ts
    for page in range(MAX_PAGES):
        r = s.get(API, params={"page": page, "size": SIZE}, timeout=60)
        r.raise_for_status()
        pages += 1
        items = (r.json() or {}).get("content") or []
        if not items:
            break
        out += parse(items, ts, ts)
        oldest = min(oldest, min((x.get("publicatieDatum") or ts) for x in items))
        if oldest < stop:
            break
        time.sleep(1)
    if pages and not out and oldest >= ts:
        raise RuntimeError("TenderNed: nothing read; previous snapshot kept")
    best = {}
    for x in out:   # one tender (kenmerk) can have a notice and later rectifications: keep the newest publication
        if x["id"] not in best or x["_pub"] > best[x["id"]]["_pub"]:
            best[x["id"]] = x
    rows = [{k: v for k, v in x.items() if k != "_pub"} for x in best.values()]
    rows, q = quarantine_future(rows, "tenderned")
    keep, _ = snapshot("tenderned", rows)
    log.info("TenderNed: %d open national notices (%d pages back to %s)", len(keep), pages, oldest)
    return keep, {"new": len(keep), "pages": pages, "quarantined": q, "complete_snapshot": 1 if oldest < stop else 0}
