"""Probe candidate tender portals (Africa / MENA): status, size, and a saved sample of each page."""
import os, re, sys
sys.path.insert(0, ".")
from curl_cffi import requests as cr
s = cr.Session(impersonate="chrome")
os.makedirs("data/probe/portals", exist_ok=True)
URLS = {
    "ma_list": "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons",
    "ma_home": "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseHome",
    "ma_rss": "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseRss",
    "et_home": "https://egp.ppa.gov.et/egp/bids/all/tenders/open",
    "et_api": "https://egp.ppa.gov.et/po-gw/cms/api/tenders?page=0&size=10",
    "et_api2": "https://egp.ppa.gov.et/egp-gw/api/tenders/open?page=0&size=10",
    "eg_home": "https://etenders.gov.eg/Tender/DoSearch",
    "eg_root": "https://etenders.gov.eg/",
    "gh_ghaneps": "https://www.ghaneps.gov.gh/epps/quickSearchAction.do?searchSelect=11",
    "ng_bpp": "https://www.bpp.gov.ng/category/procurement-notices/",
    "tn_tuneps": "https://www.tuneps.tn/portail/consultations",
    "dz_bomop": "https://www.bomop.dz/",
    "jo_jonep": "https://www.jonepps.gov.jo/",
    "rw_umucyo": "https://www.umucyo.gov.rw/eb/bav/selectListAdvertisingListForGU.do",
    "ug_egp": "https://egpuganda.go.ug/bid-notices",
    "tz_nest": "https://nest.go.tz/tenders/published",
    "ci_marches": "https://www.marchespublics.ci/appel_offre",
    "sn_marches": "https://www.marchespublics.sn/index.php?option=com_avis&task=avis_appel_offre",
}
for k, u in URLS.items():
    try:
        r = s.get(u, timeout=40)
        t = r.text
        open(f"data/probe/portals/{k}.html", "w", encoding="utf-8").write(t[:400000])
        title = re.search(r"<title>(.*?)</title>", t, re.S | re.I)
        print(k, r.status_code, len(t), (title.group(1).strip()[:80] if title else ""), "| ct", r.headers.get("content-type"), flush=True)
    except Exception as e:
        print(k, "ERR", str(e)[:150], flush=True)
