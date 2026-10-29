import json, re
from pathlib import Path
from curl_cffi import requests as cr
s = cr.Session(impersonate="chrome", timeout=40)
out = []
def get(u, **kw):
    try:
        r = s.get(u, **kw); return r.status_code, r.headers.get("content-type", ""), r.text
    except Exception as e:
        return "ERR", "", str(e)
# NYC City Record (Socrata)
c, ct, t = get("https://data.cityofnewyork.us/resource/dg92-zbpx.json", params={"$limit": 3, "$order": "start_date DESC", "section_name": "Procurement"})
out.append(f"NYC {c} {t[:2500]}")
c, ct, t = get("https://data.cityofnewyork.us/resource/dg92-zbpx.json", params={"$select": "count(*)", "$where": "section_name='Procurement' AND due_date > '2026-10-29'"})
out.append(f"NYC open count {c} {t[:300]}")
for name, u in [("TX ESBD", "https://www.txsmartbuy.gov/esbd"), ("FL VBS", "https://vendor.myfloridamarketplace.com/search/bids"),
                ("CA eProcure", "https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx"),
                ("MTA", "https://new.mta.info/doing-business-with-us/procurement"), ("PANYNJ", "https://www.panynj.gov/port-authority/en/business-opportunities/solicitations-advertisements.html"),
                ("LA Metro", "https://business.metro.net/webcenter/portal/VendorPortal/pages_home/solicitations/openSolicitations"),
                ("IDB", "https://www.iadb.org/en/how-we-can-work-together/procurement/procurement-projects/project-procurement"),
                ("IDB notices", "https://projectprocurement.iadb.org/en/procurement-notices"),
                ("IMF", "https://www.imf.org/en/About/procurement")]:
    c, ct, t = get(u)
    links = re.findall(r'https?://[^"\']+(?:api|json|service|search)[^"\']{0,80}', t)[:8]
    out.append(f"{name} {c} {ct} len={len(t)} title={re.search(r'<title>(.*?)</title>', t, re.S).group(1).strip()[:80] if '<title>' in t else ''} links={links}")
Path("data/probe/us_probe.txt").write_text("\n".join(out))
