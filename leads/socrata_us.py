"""US state and local open bids published as open data on Socrata portals (SODA API, no key, published for reuse).
Each dataset is mapped field by field; a dataset joins only when it lists CURRENT bids with a closing date.

  Delaware   data.delaware.gov 2hnj-zwix 'Open Bids' (state agencies and school districts; link to mmp.delaware.gov)

Checked 2026-11-14. Candidates found through the Socrata catalog and left out: Mesa AZ (no closing date), Montgomery
County MD (owner decision on its terms pending), New York datasets (history, not open bids)."""
import re

from .common import clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

DATASETS = [  # key, url, state, buyer default, field map
    ("de", "https://data.delaware.gov/resource/2hnj-zwix.json", "US-DE", "State of Delaware",
     {"id": "contractnumber", "title": "contracttitle", "pub": "opendate", "deadline": "deadlinedate", "agency": "agencycode", "link": "bidurl"}),
]


def _link(v):
    return (v.get("url") if isinstance(v, dict) else v) or ""


def fetch():
    s, t = session(), str(today())
    out, meta = [], {}
    for key, url, state, buyer, f in DATASETS:
        try:
            r = s.get(url, params={"$limit": 5000}, timeout=60)
            r.raise_for_status()
            items = r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("Socrata %s: %s", key, str(e)[:120]); meta[f"{key}_failed"] = 1; continue
        n = 0
        for x in items:
            no, title = clean(str(x.get(f["id"]) or "")), clean(x.get(f["title"]) or "")
            dl = (x.get(f["deadline"]) or "")[:10]
            if not no or not title or not dl or dl < t:
                continue
            agency = clean(x.get(f["agency"]) or "")
            sector, how = classify(title)
            out.append({"id": f"SOC-{key.upper()}-" + re.sub(r"[^A-Za-z0-9]+", "-", no)[:80], "source": f"{buyer} open bids (open data)",
                        "group": "", "sector": sector, "nature": "", "cpv": "", "classification": how, "country": "USA",
                        "buyer": (f"{buyer} ({agency})" if agency else buyer)[:120], "title": title[:300],
                        "notice_type": "Open bid", "stage": "tender", "region_code": state,
                        "access": "State supplier registration usually needed to respond", "published": (x.get(f["pub"]) or "")[:10],
                        "deadline": dl, "deadline_basis": "submission", "value": "", "currency": "",
                        "link": _link(x.get(f["link"])) or url, "source_url": url, "fetched": t, "contact": "", "lang": "en"})
            n += 1
        meta[f"{key}_open"] = n
    if not out and any(k.endswith("_failed") for k in meta):
        raise RuntimeError("Socrata open bids: nothing read; previous snapshot kept")
    out, q = quarantine_future(out, "socrata_us")
    keep, _ = snapshot("socrata_us", list({x["id"]: x for x in out}.values()))
    log.info("Socrata open bids: %d open (%s)", len(keep), ", ".join(f"{k} {v}" for k, v in meta.items()))
    meta.update(new=len(keep), quarantined=q, parts_failed=sum(1 for k in meta if k.endswith("_failed")))
    return keep, meta
