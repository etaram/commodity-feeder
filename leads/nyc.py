"""New York City: open procurement solicitations from the City Record Online (NYC Open Data, Socrata API, no key).
NYC is the largest US local buyer; solicitations are generally open to any responsible bidder (check M/WBE goals,
local law and Buy American clauses in each notice)."""
import html
import re

from .common import clean, log, session, today
from .sectors import classify
from .taxonomy import group_of_text

URL = "https://data.cityofnewyork.us/resource/dg92-zbpx.json"


def fetch():
    s, t = session(), today()
    rows, off = [], 0
    where = f"section_name='Procurement' AND due_date >= '{t}T00:00:00' AND type_of_notice_description like '%Solicitation%'"
    while off < 5000:
        try:
            res = s.get(URL, params={"$where": where, "$limit": 1000, "$offset": off, "$order": "start_date DESC"}, timeout=60).json()
        except Exception as e:  # noqa: BLE001
            log.warning("NYC City Record: %s", e); break
        if not isinstance(res, list) or not res:
            break
        for o in res:
            title = clean(html.unescape(o.get("short_title") or ""))
            desc = clean(re.sub(r"<[^>]+>", " ", html.unescape(o.get("additional_description_1") or "")), 600)
            cat = o.get("category_description") or ""
            sector, method = classify(f"{title} {desc[:200]}")
            amt = o.get("contract_amount")
            rows.append({
                "id": f"NYC-{o.get('request_id')}", "source": "NYC City Record (USA)",
                "group": group_of_text(title) or "", "sector": sector, "cpv": "", "country": "USA",
                "nature": "works" if "Construction" in cat else "supplies" if cat == "Goods" else "services" if "Services" in cat else "",
                "buyer": f"New York City - {o.get('agency_name') or ''}"[:120], "title": title[:300],
                "classification": method or "keyword", "notice_type": f"{o.get('type_of_notice_description', '')} | {o.get('selection_method_description', '')}"[:120],
                "stage": "tender", "access": "US local government: open to responsible bidders (check M/WBE and Buy American clauses)",
                "published": (o.get("start_date") or "")[:10], "deadline": (o.get("due_date") or "")[:10],
                "value": float(amt) if amt not in (None, "", "0") else "", "currency": "USD" if amt not in (None, "", "0") else "",
                "link": f"https://a856-cityrecord.nyc.gov/RequestDetail/{o.get('request_id')}", "contact": o.get("email") or "",
                "lang": "",
            })
        if len(res) < 1000:
            break
        off += 1000
    log.info("NYC City Record open solicitations: %d", len(rows))
    return rows, {"open": len(rows)}
