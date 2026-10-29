"""US cities: open solicitations of the 20 largest US cities (New York City has its own module, leads/nyc.py).

Adapters, best first: open data API (Los Angeles RAMP on Socrata), the Bonfire public portal feed (Fort Worth,
Charlotte, San Antonio ...), else the city's own bids page read with leads.web_tenders (robots.txt respected).
Cities whose portal only renders in a browser (JavaScript apps) are reported as such in the meta, not scraped.
"""
import html
import re

from .common import clean, log, session, today
from .sectors import classify
from .taxonomy import group_of_text

ACCESS = "US local government: open to responsible bidders (check local preference, M/WBE and Buy America clauses)"
CITIES = [  # (city, adapters)
    ("Los Angeles", [("socrata", "https://data.lacity.org/resource/hf3r-utnq.json")]),
    ("Chicago", [("html", "https://www.chicago.gov/city/en/depts/dps/isupplier/current-bids.html")]),
    ("Houston", [("html", "https://www.houstontx.gov/obo/current_contracting_opportunities.html")]),
    ("Phoenix", [("html", "https://solicitations.phoenix.gov/")]),
    ("Philadelphia", [("html", "https://www.phlcontracts.phila.gov/bso/external/publicBids.sdo"),
                      ("html", "https://www.phila.gov/departments/procurement-department/")]),
    ("San Antonio", [("bonfire", "sanantonio"), ("html", "https://webapp1.sanantonio.gov/BidContractOpps/Default.aspx")]),
    ("San Diego", [("html", "https://www.sandiego.gov/purchasing/bids-contracts")]),
    ("Dallas", [("html", "https://dallascityhall.com/departments/procurement/Pages/bid_opportunities.aspx"),
                ("html", "https://dallascityhall.com/departments/procurement/Pages/default.aspx")]),
    ("Jacksonville", [("html", "https://www.jacksonville.gov/departments/office-of-administrative-services/procurement")]),
    ("Fort Worth", [("bonfire", "fortworthtexas")]),
    ("Austin", [("html", "https://financeonline.austintexas.gov/afo/account_services/solicitation/solicitations.cfm")]),
    ("San Jose", [("html", "https://www.sanjoseca.gov/your-government/departments-offices/finance/purchasing/bid-opportunities")]),
    ("Charlotte", [("bonfire", "charlottenc")]),
    ("Columbus", [("html", "https://www.columbus.gov/Business-Development/Bids-Solicitations/RFPs"),
                  ("html", "https://www.columbus.gov/Government/Departments/Finance-and-Management/Purchasing-Office")]),
    ("Indianapolis", [("html", "https://www.indy.gov/agency/purchasing-division"), ("html", "https://www.indy.gov/activity/bid-on-city-contracts")]),
    ("San Francisco", [("js", "https://sfcitypartner.sfgov.org/pages/Events-BS3/event-search.aspx")]),
    ("Seattle", [("html", "https://www.seattle.gov/purchasing-and-contracting")]),
    ("Denver", [("html", "https://www.denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/General-Services/Purchasing")]),
    ("Oklahoma City", [("hosted", "https://bidnetdirect.com/cityofoklahomacityandtrusts")]),
    ("Nashville", [("html", "https://www.nashville.gov/departments/finance/procurement")]),
]


def _row(city, uid, title, deadline, link, notice="", dept="", value="", published="", contact="", nature=""):
    title = clean(html.unescape(title or ""))
    sector, method = classify(title)
    return {"id": f"USC-{re.sub(r'[^A-Za-z0-9]', '', city)[:12]}-{uid}"[:80], "source": f"US city - {city}",
            "group": group_of_text(title) or "", "sector": sector, "cpv": "", "country": "USA", "nature": nature,
            "buyer": f"City of {city}" + (f" - {dept}" if dept else ""), "title": title[:300], "classification": method or "keyword",
            "notice_type": notice[:120], "stage": "tender", "access": ACCESS, "published": published, "deadline": deadline,
            "value": value, "currency": "USD" if value else "", "link": link, "contact": contact, "lang": ""}


def _socrata(city, url, t):
    res = session().get(url, params={"$limit": 2000}, timeout=60).json()
    out = []
    for o in res if isinstance(res, list) else []:
        if (o.get("stagename") or "Open").lower() not in ("open", "active", "published"):
            continue
        due = next((str(v)[:10] for k, v in o.items() if re.search(r"due|close|deadline", k, re.I) and v), "")
        if due and due < str(t):
            continue
        uid = o.get("rampid") or o.get("id") or abs(hash(o.get("title", ""))) % 10**9
        out.append(_row(city, uid, o.get("title"), due, f"https://www.rampla.org/s/opportunity/{uid}" if o.get("rampid") else url,
                        o.get("type", ""), o.get("department") or o.get("agency") or "", published=str(o.get("bidpost") or "")[:10]))
    return out


def _bonfire(city, org, t):
    s = session()
    j = s.get(f"https://{org}.bonfirehub.com/PublicPortal/getOpenPublicOpportunitiesSectionData", timeout=60,
              headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}).json()
    out = []
    for p in ((j.get("payload") or {}).get("projects") or {}).values():
        close = str(p.get("DateClose") or p.get("CloseDate") or "")[:10]
        if close and close < str(t):
            continue
        pid = p.get("ProjectID")
        out.append(_row(city, pid, p.get("ProjectName") or p.get("Name") or p.get("ReferenceID"), close,
                        f"https://{org}.bonfirehub.com/opportunities/{pid}", f"Bonfire {p.get('ReferenceID', '')}",
                        p.get("DepartmentName") or "", published=str(p.get("DateOpen") or "")[:10]))
    return out


def _html(city, url, t):
    from .web_tenders import scan_page
    page, items, st = scan_page(url, depth=2)
    out = []
    for it in items:
        uid = re.sub(r"[^A-Za-z0-9]", "", it["number"])[:20] or str(abs(hash(it["title"])) % 10**9)
        out.append(_row(city, uid, it["title"], it["deadline"], it["link"], f"Solicitation {it['number']}".strip()))
    return out, page, st


def fetch():
    t, rows, meta = today(), [], {}
    for city, adapters in CITIES:
        got, note = [], ""
        for kind, arg in adapters:
            try:
                if kind == "socrata":
                    got = _socrata(city, arg, t); note = "open data API"
                elif kind == "bonfire":
                    got = _bonfire(city, arg, t); note = "Bonfire portal"
                elif kind == "html":
                    got, page, st = _html(city, arg, t); note = f"web page {st}: {page}"
                elif kind == "hosted":
                    note = "bids hosted on a commercial platform that requires registration: not scanned"
                else:
                    note = "portal needs a browser (JavaScript): not scanned"
            except Exception as e:  # noqa: BLE001
                note = f"{kind} failed: {type(e).__name__}"
            if got:
                break
        meta[city] = f"{len(got)} | {note}"[:160]
        rows += got
        log.info("US city %s: %d (%s)", city, len(got), note)
    seen, uniq = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"]); uniq.append(r)
    log.info("US cities: %d open solicitations from %d cities", len(uniq), sum(1 for v in meta.values() if not v.startswith("0 ")))
    return uniq, {k.replace(" ", "_"): v for k, v in meta.items()}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    r, m = fetch()
    for k, v in m.items():
        print(k, v)
