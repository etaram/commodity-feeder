"""IDB contract awards: who won the contracts the Inter-American Development Bank finances (data.iadb.org dataset
"IDB Project Procurement Contract Awards Data", resource dd09c605-9cd8-49c5-92dc-191ff6ecdd58, CC BY 4.0;
robots.txt of data.iadb.org allows the API, checked 2026-11-12). ~160,000 contracts with the awarded firm's name,
country, city and address, the executing agency, amount and signature date.

The procurement notices dataset that leads/iadb.py reads has award notifications too, but without the winner (a PDF
link only), so iadb.py keeps skipping them and this module reads the awards dataset instead.

First run: contracts signed since START (back-fill, paged); later runs: rows modified since the last run.
Writes award day files data/leads/awards/iadb/YYYY-MM-DD.json (by signature date; firm addresses go to the private
contacts file like every award source). Signature dates in the future are quarantined."""
import datetime as dt
import json

from .common import PRIVATE, clean, log, polite, quarantine_future, save_awards, session, today
from .regions import iso3
from .sectors import classify

RESOURCE = "dd09c605-9cd8-49c5-92dc-191ff6ecdd58"
SQL = "https://data.iadb.org/api/action/datastore_search_sql"
SOURCE_URL = "https://data.iadb.org/dataset/idb-project-procurement-contract-awards-data"
START = "2019-01-01"
PAGE = 5000
KEEP_DAYS = 365 * 8
STATE = PRIVATE / "iadb_awards_state.json"


def to_row(x, fetched):
    pub = (x.get("signature_date") or x.get("entry_date") or "")[:10]
    firm = clean(x.get("awarded_firm_name"), 160)
    if not firm:
        return None
    wc = iso3((x.get("awarded_firm_country_code") or "").upper()) or iso3((x.get("awarded_firm_country_name") or "").title()) or ""
    bc = iso3((x.get("operation_country_code") or "").upper()) or iso3((x.get("operation_country_name") or "").title()) or ""
    title = clean(f"{x.get('contract_type') or ''}: {x.get('project_name') or ''}", 200).strip(": ")
    sector, _ = classify(f"{x.get('project_name') or ''} | {x.get('economic_sector_name') or ''} | {x.get('contract_type') or ''}")
    try:
        val = float(x.get("total_amount") or x.get("idb_amount") or 0) or ""
    except ValueError:
        val = ""
    proj = x.get("project_number") or ""
    return {
        "id": f"IDBA-{x.get('contract_id') or x.get('_id')}-{x.get('_id')}", "source": "IDB contract awards", "group": "", "sector": sector,
        "title": title, "buyer": clean(x.get("executing_agency") or x.get("borrower_name"), 120), "country": bc, "cpv": "",
        "published": pub, "winners": [firm], "winner_country": wc, "winner_size": "", "value": val, "currency": "USD" if val else "",
        "bids": "", "email": "", "link": f"https://www.iadb.org/en/project/{proj}" if proj else SOURCE_URL, "source_url": SOURCE_URL,
        "fetched": fetched, "procurement_type": clean(x.get("procurement_type"), 60), "project": proj,
        "contacts": [{"name": firm, "country": wc, "address": clean(f"{x.get('awarded_firm_address') or ''} {x.get('awarded_firm_city') or ''}", 200)}],
    }


def fetch():
    s, t = session(), str(today())
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    since = st.get("modified_since")
    where = f"\"last_modification_date\" >= '{since}'" if since else f"\"signature_date\" >= '{START}'"
    rows, offset, newest = [], 0, since or ""
    while True:
        q = f'SELECT * FROM "{RESOURCE}" WHERE {where} ORDER BY "_id" LIMIT {PAGE} OFFSET {offset}'
        r = s.get(SQL, params={"sql": q}, timeout=120)
        r.raise_for_status()
        recs = r.json()["result"]["records"]
        for x in recs:
            a = to_row(x, t)
            if a:
                rows.append(a)
            newest = max(newest, (x.get("last_modification_date") or "")[:10])
        log.info("IDB awards page %d: %d records", offset // PAGE, len(recs))
        if len(recs) < PAGE:
            break
        offset += PAGE
        polite(1.5)
    rows, quarantined = quarantine_future(rows, "iadb_awards")
    n = save_awards("iadb", rows, keep_days=KEEP_DAYS) if rows else 0
    PRIVATE.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"modified_since": newest or t, "run": t}))
    log.info("IDB awards: %d contracts with a winner (since %s), %d quarantined", n, since or START, quarantined)
    return [], {"awards": n, "quarantined": quarantined, "since": since or START}
