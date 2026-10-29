import re, json
from pathlib import Path
from curl_cffi import requests as cr
s = cr.Session(impersonate="chrome", timeout=30)
out = []
KW = re.compile(r"\b(RFP|RFQ|IFB|ITB|RFI|solicitation|bid|proposal)s?\b", re.I)
def probe(name, u, **kw):
    try:
        r = s.get(u, **kw); t = r.text
        out.append(f"{name} | {r.status_code} | len={len(t)} | kw={len(KW.findall(t))} | {str(r.url)[:100]} | {re.sub(r'\s+',' ',t[:200])!r}")
        return t
    except Exception as e:
        out.append(f"{name} | ERR {type(e).__name__} {str(e)[:100]} | {u}")
probe("LA socrata", "https://data.lacity.org/resource/hf3r-utnq.json", params={"$limit": 2})
for org in ["dallascitypurchasing", "fortworthtexas", "charlottenc", "denver", "okc", "indianapolis", "jacksonville", "sanjose",
            "columbusoh", "sandiego", "austintexas", "phoenix", "cityofchicago", "houstontx", "seattle", "sanantonio", "sfgov", "philadelphia"]:
    probe(f"bonfire {org}", f"https://{org}.bonfirehub.com/PublicPortal/getOpenPublicOpportunitiesSectionData")
for name, u in [("Chicago", "https://www.chicago.gov/city/en/depts/dps/isupplier/current-bids.html"),
                ("Houston OBO", "https://www.houstontx.gov/obo/current_contracting_opportunities.html"),
                ("Houston purchasing", "https://purchasing.houstontx.gov/"),
                ("Phoenix", "https://solicitations.phoenix.gov/"),
                ("Philadelphia BuySpeed", "https://www.phlcontracts.phila.gov/bso/external/publicBids.sdo"),
                ("San Antonio", "https://webapp1.sanantonio.gov/BidContractOpps/Default.aspx"),
                ("San Diego", "https://www.sandiego.gov/purchasing/bids-contracts"),
                ("Jacksonville", "https://www.coj.net/departments/finance/procurement"),
                ("Austin", "https://financeonline.austintexas.gov/afo/account_services/solicitation/solicitations.cfm"),
                ("San Jose", "https://www.sanjoseca.gov/your-government/departments-offices/finance/purchasing-risk-management"),
                ("Charlotte", "https://www.charlottenc.gov/Departments/Procurement"),
                ("Columbus", "https://www.columbus.gov/Business-Development/Doing-Business-with-the-City"),
                ("Indianapolis", "https://www.indy.gov/agency/office-of-minority-and-women-business-development"),
                ("SF", "https://sfcitypartner.sfgov.org/pages/Events-BS3/event-search.aspx"),
                ("Seattle", "https://www.seattle.gov/purchasing-and-contracting"),
                ("Denver", "https://www.denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/General-Services/Purchasing"),
                ("OKC", "https://www.okc.gov/departments/finance/purchasing"),
                ("Fort Worth", "https://www.fortworthtexas.gov/departments/finance/purchasing"),
                ("Dallas", "https://dallascityhall.com/departments/procurement/Pages/default.aspx")]:
    probe(name, u)
Path("data/probe/us_probe.txt").write_text("\n".join(out))
