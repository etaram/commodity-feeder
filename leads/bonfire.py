"""Bonfire (Euna Procurement) public portals: many public bodies in the US and Canada publish their open bids on a
Bonfire hub, https://<hub>.bonfirehub.com/portal/?tab=openOpportunities. The hub page loads its list from one public
JSON call, /PublicPortal/getOpenPublicOpportunitiesSectionData: reference, project name, closing date and time,
project id. The first hub, the Port Authority of New York and New Jersey (Grok, 13 Nov 2026), had 87 open.

Hubs are listed in HUBS (hub, buyer name, ISO country). A hub name that is wrong or no longer used returns an error
or no 'success' and is skipped; the run log prints how many hubs answered, so wrong guesses cost one request each.
Access (checked 2026-11-13 from the server, panynj): public, no sign-in; Bonfire vendor registration is needed to
download some documents and to bid, not to read the list. One request per hub per run."""
import html
import re
import time

from .common import clean, log, quarantine_future, rolling, session, today
from .sectors import classify

# (hub, buyer, country). Only public bodies (port authorities, cities, counties, states, utilities, schools).
HUBS = [
    ("panynj", "Port Authority of New York and New Jersey", "USA"),
    ("fortworthtexas", "City of Fort Worth, Texas", "USA"),
    ("sedona", "City of Sedona, Arizona", "USA"),
    ("bendoregon", "City of Bend, Oregon", "USA"),
    ("siouxfalls", "City of Sioux Falls, South Dakota", "USA"),
    ("bouldercolorado", "City of Boulder, Colorado", "USA"),
    ("scrantonpa", "City of Scranton, Pennsylvania", "USA"),
    ("talgov", "City of Tallahassee, Florida", "USA"),
    ("amarillo", "City of Amarillo, Texas", "USA"),
    ("mrsc", "MRSC Washington public agencies", "USA"),
    ("whitehorse", "City of Whitehorse, Yukon", "CAN"),
    ("victoria", "City of Victoria, British Columbia", "CAN"),
    ("fnha", "First Nations Health Authority, British Columbia", "CAN"),
    ("portoflosangeles", "Port of Los Angeles", "USA"),
    ("portofseattle", "Port of Seattle", "USA"),
    ("dfw", "Dallas Fort Worth International Airport", "USA"),
    ("austintexas", "City of Austin, Texas", "USA"),
    ("denvergov", "City and County of Denver", "USA"),
    ("cityofboise", "City of Boise, Idaho", "USA"),
    ("kcmo", "City of Kansas City, Missouri", "USA"),
    ("charlottenc", "City of Charlotte, North Carolina", "USA"),
    ("raleighnc", "City of Raleigh, North Carolina", "USA"),
    ("nashville", "Metro Nashville", "USA"),
    ("tucsonaz", "City of Tucson, Arizona", "USA"),
    ("phoenix", "City of Phoenix, Arizona", "USA"),
    ("mesaaz", "City of Mesa, Arizona", "USA"),
    ("saskatoon", "City of Saskatoon", "CAN"),
    ("regina", "City of Regina", "CAN"),
    ("halifax", "Halifax Regional Municipality", "CAN"),
    ("calgary", "City of Calgary", "CAN"),
    ("edmonton", "City of Edmonton", "CAN"),
    ("cityofkelowna", "City of Kelowna", "CAN"),
    ("nanaimo", "City of Nanaimo", "CAN"),
    ("saanich", "District of Saanich", "CAN"),
    ("ubc", "University of British Columbia", "CAN"),
    ("bchydro", "BC Hydro", "CAN"),
    ("translink", "TransLink", "CAN"),
    ("metrovancouver", "Metro Vancouver", "CAN"),
    ("cityofmarkham", "City of Markham", "CAN"),
    ("brampton", "City of Brampton", "CAN"),
    ("mississauga", "City of Mississauga", "CAN"),
    ("hamilton", "City of Hamilton", "CAN"),
    ("london", "City of London, Ontario", "CAN"),
    ("waterloo", "Region of Waterloo", "CAN"),
    ("guelph", "City of Guelph", "CAN"),
    ("kingston", "City of Kingston", "CAN"),
    ("barrie", "City of Barrie", "CAN"),
    ("oshawa", "City of Oshawa", "CAN"),
    ("durham", "Region of Durham", "CAN"),
    ("yorkregion", "York Region", "CAN"),
    ("peelregion", "Region of Peel", "CAN"),
    ("ottawa", "City of Ottawa", "CAN"),
    ("gatineau", "Ville de Gatineau", "CAN"),
    ("fredericton", "City of Fredericton", "CAN"),
    ("moncton", "City of Moncton", "CAN"),
    ("stjohns", "City of St. John's", "CAN"),
    ("winnipeg", "City of Winnipeg", "CAN"),
    ("cityofsurrey", "City of Surrey", "CAN"),
    ("burnaby", "City of Burnaby", "CAN"),
    ("richmond", "City of Richmond, British Columbia", "CAN"),
    ("coquitlam", "City of Coquitlam", "CAN"),
    ("langley", "Township of Langley", "CAN"),
    ("abbotsford", "City of Abbotsford", "CAN"),
    ("kamloops", "City of Kamloops", "CAN"),
    ("princegeorge", "City of Prince George", "CAN"),
    ("lethbridge", "City of Lethbridge", "CAN"),
    ("reddeer", "City of Red Deer", "CAN"),
    ("medicinehat", "City of Medicine Hat", "CAN"),
    ("strathcona", "Strathcona County", "CAN"),
    ("airdrie", "City of Airdrie", "CAN"),
    ("albertahealthservices", "Alberta Health Services", "CAN"),
    ("epcor", "EPCOR Utilities", "CAN"),
    ("enmax", "ENMAX", "CAN"),
    ("ttc", "Toronto Transit Commission", "CAN"),
    ("metrolinx", "Metrolinx", "CAN"),
    ("novascotia", "Province of Nova Scotia", "CAN"),
    ("yukon", "Government of Yukon", "CAN"),
    ("nwt", "Government of the Northwest Territories", "CAN"),
    ("nunavut", "Government of Nunavut", "CAN"),
    ("detroitmi", "City of Detroit, Michigan", "USA"),
    ("cityofdetroit", "City of Detroit, Michigan", "USA"),
    ("columbus", "City of Columbus, Ohio", "USA"),
    ("cincinnati-oh", "City of Cincinnati, Ohio", "USA"),
    ("pittsburghpa", "City of Pittsburgh, Pennsylvania", "USA"),
    ("baltimorecity", "City of Baltimore, Maryland", "USA"),
    ("richmondgov", "City of Richmond, Virginia", "USA"),
    ("norfolk", "City of Norfolk, Virginia", "USA"),
    ("jaxport", "Jacksonville Port Authority", "USA"),
    ("portofhouston", "Port Houston", "USA"),
    ("portoflongbeach", "Port of Long Beach", "USA"),
    ("portofoakland", "Port of Oakland", "USA"),
    ("portoftacoma", "Port of Tacoma", "USA"),
    ("portofportland", "Port of Portland", "USA"),
    ("massport", "Massachusetts Port Authority", "USA"),
    ("mwaa", "Metropolitan Washington Airports Authority", "USA"),
    ("flyontario", "Ontario International Airport Authority", "USA"),
    ("sandiego", "City of San Diego", "USA"),
    ("sanjoseca", "City of San Jose", "USA"),
    ("oaklandca", "City of Oakland", "USA"),
    ("sacramento", "City of Sacramento", "USA"),
    ("fresno", "City of Fresno", "USA"),
    ("longbeach", "City of Long Beach", "USA"),
    ("santaana", "City of Santa Ana", "USA"),
    ("riversideca", "City of Riverside", "USA"),
    ("lasvegasnevada", "City of Las Vegas", "USA"),
    ("renonv", "City of Reno", "USA"),
    ("saltlakecity", "Salt Lake City", "USA"),
    ("albuquerque", "City of Albuquerque", "USA"),
    ("elpasotexas", "City of El Paso", "USA"),
    ("sanantonio", "City of San Antonio", "USA"),
    ("houstontx", "City of Houston", "USA"),
    ("dallascitynews", "City of Dallas", "USA"),
    ("arlingtontx", "City of Arlington, Texas", "USA"),
    ("plano", "City of Plano", "USA"),
    ("okc", "City of Oklahoma City", "USA"),
    ("tulsa", "City of Tulsa", "USA"),
    ("wichita", "City of Wichita", "USA"),
    ("omaha", "City of Omaha", "USA"),
    ("desmoines", "City of Des Moines", "USA"),
    ("minneapolis", "City of Minneapolis", "USA"),
    ("stpaul", "City of Saint Paul", "USA"),
    ("milwaukee", "City of Milwaukee", "USA"),
    ("madison", "City of Madison", "USA"),
    ("indy", "City of Indianapolis", "USA"),
    ("louisvilleky", "Louisville Metro", "USA"),
    ("lexingtonky", "Lexington-Fayette Urban County", "USA"),
    ("memphistn", "City of Memphis", "USA"),
    ("knoxville", "City of Knoxville", "USA"),
    ("atlanta", "City of Atlanta", "USA"),
    ("savannah", "City of Savannah", "USA"),
    ("orlando", "City of Orlando", "USA"),
    ("tampa", "City of Tampa", "USA"),
    ("miamidade", "Miami-Dade County", "USA"),
    ("fortlauderdale", "City of Fort Lauderdale", "USA"),
    ("neworleans", "City of New Orleans", "USA"),
    ("birminghamal", "City of Birmingham, Alabama", "USA"),
    ("charleston-sc", "City of Charleston, South Carolina", "USA"),
    ("greensboro-nc", "City of Greensboro", "USA"),
    ("durhamnc", "City of Durham, North Carolina", "USA"),
    ("virginiabeach", "City of Virginia Beach", "USA"),
    ("providenceri", "City of Providence", "USA"),
    ("hartford", "City of Hartford", "USA"),
    ("bostonma", "City of Boston", "USA"),
    ("buffalony", "City of Buffalo", "USA"),
    ("rochesterny", "City of Rochester, New York", "USA"),
    ("newarknj", "City of Newark, New Jersey", "USA"),
    ("jerseycitynj", "Jersey City", "USA"),
    ("philadelphia", "City of Philadelphia", "USA"),
    ("anchorage", "Municipality of Anchorage", "USA"),
    ("honolulu", "City and County of Honolulu", "USA"),
    ("spokanecity", "City of Spokane", "USA"),
    ("tacoma", "City of Tacoma", "USA"),
    ("seattle", "City of Seattle", "USA"),
    ("kingcounty", "King County", "USA"),
    ("portlandoregon", "City of Portland, Oregon", "USA"),
    ("eugene", "City of Eugene", "USA"),
    ("coloradosprings", "City of Colorado Springs", "USA"),
    ("aurora", "City of Aurora, Colorado", "USA"),
    ("fortcollins", "City of Fort Collins", "USA"),
    # 13 Nov: hubs seen in search results (real Bonfire subdomains) and agencies that link to a Bonfire portal
    ("caribbeanclimate", "Caribbean Community Climate Change Centre", "BLZ"),
    ("leandertx", "City of Leander, Texas", "USA"),
    ("hcpss", "Howard County Public School System, Maryland", "USA"),
    ("dart", "Dallas Area Rapid Transit", "USA"),
    ("sandysprings", "City of Sandy Springs, Georgia", "USA"),
    ("louisvillemsd", "Louisville Metropolitan Sewer District", "USA"),
    ("milwaukieoregon", "City of Milwaukie, Oregon", "USA"),
    ("putnamcountyny", "Putnam County, New York", "USA"),
    ("uncfsu", "Fayetteville State University", "USA"),
    ("txdot", "Texas Department of Transportation", "USA"),
    ("owensboro", "City of Owensboro, Kentucky", "USA"),
    ("leeschools", "Lee County School District, Florida", "USA"),
    ("aps", "Albuquerque Public Schools", "USA"),
    ("psta", "Pinellas Suncoast Transit Authority", "USA"),
    ("johnsoncountytx", "Johnson County, Texas", "USA"),
    ("parkercountytx", "Parker County, Texas", "USA"),
    ("losalamosnm", "Los Alamos County, New Mexico", "USA"),
    ("bouldercounty", "Boulder County, Colorado", "USA"),
    ("columbiacountyga", "Columbia County, Georgia", "USA"),
    ("capecod", "Barnstable County, Massachusetts", "USA"),
    ("bannockcounty", "Bannock County, Idaho", "USA"),
    ("harfordcountymd", "Harford County, Maryland", "USA"),
    ("harfordcounty", "Harford County, Maryland", "USA"),
    ("vernon", "City of Vernon, British Columbia", "CAN"),
    ("nelson", "City of Nelson, British Columbia", "CAN"),
    ("mission", "District of Mission, British Columbia", "CAN"),
    ("austinisd", "Austin Independent School District", "USA"),
    ("rochesterschools", "Rochester Public Schools, Minnesota", "USA"),
    ("westada", "West Ada School District, Idaho", "USA"),
    ("tomballisd", "Tomball ISD, Texas", "USA"),
    ("d11", "Colorado Springs School District 11", "USA"),
    ("alleghenycounty", "Allegheny County, Pennsylvania", "USA"),
    ("jordandistrict", "Jordan School District, Utah", "USA"),
    ("utexas", "University of Texas at Austin", "USA"),
    ("louisville", "Louisville Metro Government", "USA"),
]
BAD_STATUS = re.compile(r"cancel|award|closed", re.I)


def _date(s):
    m = re.match(r"(20\d\d-\d\d-\d\d)", str(s or ""))
    return m.group(1) if m else ""


def _org(s, hub):
    try:
        r = s.get(f"https://{hub}.bonfirehub.com/portal/?tab=openOpportunities", timeout=30)
        m = re.search(r"<title>(.*?)</title>", r.text, re.S)
    except Exception:  # noqa: BLE001
        return ""
    name = clean(html.unescape(m.group(1))) if m else ""
    name = re.sub(r"\s*[-|]\s*(Bonfire|Euna).*$|^(Bonfire|Euna Procurement)\s*[-|]\s*|\s*Public Portal\s*", "", name, flags=re.I).strip(" -|")
    return name if 3 <= len(name) <= 120 else ""


def parse(js, hub, buyer, country, fetched):
    rows = []
    pay = (js or {}).get("payload") or {}
    projects = pay.get("projects") or {}
    if isinstance(projects, dict):
        projects = list(projects.values())
    for p in projects:
        pid = clean(str(p.get("ProjectID") or ""))
        name = clean(p.get("ProjectName") or "")
        if not pid or not name or str(p.get("ProjectVisibilityID", "1")) not in ("1", ""):
            continue
        ref = clean(p.get("ReferenceID") or "")
        title = name if (not ref or ref.lower() in name.lower()) else f"{ref} - {name}"
        sector, how = classify(name)
        rows.append({"id": f"BONFIRE-{hub}-{pid}", "source": f"Bonfire public portal ({hub})", "group": "", "sector": sector, "nature": "",
                     "cpv": "", "classification": how, "country": country, "buyer": buyer, "title": title[:300],
                     "notice_type": "Open public opportunity", "stage": "tender",
                     "access": "Bonfire vendor registration needed to download some documents and to bid",
                     "published": "", "deadline": _date(p.get("DateClose")), "value": "", "currency": "",
                     "link": f"https://{hub}.bonfirehub.com/opportunities/{pid}", "source_url": f"https://{hub}.bonfirehub.com/portal/?tab=openOpportunities",
                     "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def fetch():
    s = session()
    t = str(today())
    rows, answered, failed = [], [], 0
    seen = set()
    for hub, buyer, country in HUBS:
        if hub in seen:
            continue
        seen.add(hub)
        try:
            r = s.get(f"https://{hub}.bonfirehub.com/PublicPortal/getOpenPublicOpportunitiesSectionData", timeout=30,
                      headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
            js = r.json() if r.status_code == 200 else None
        except Exception:  # noqa: BLE001  (wrong hub name, DNS, not JSON)
            js = None
        if not js or not js.get("success"):
            failed += 1
            continue
        buyer = _org(s, hub) or buyer          # the hub's own name for itself, so a guessed hub never gets a wrong label
        got = parse(js, hub, buyer, country, t)
        answered.append((hub, len(got)))
        rows += got
        time.sleep(0.5)
    rows, q = quarantine_future(rows, "bonfire")
    rows = [x for x in rows if x["deadline"] and x["deadline"] >= t]    # OPEN = a future closing date
    keep, _ = rolling("bonfire", rows)
    log.info("Bonfire: %d hubs answered, %d did not; %d open; per hub: %s", len(answered), failed, len(rows),
             ", ".join(f"{h} {n}" for h, n in answered))
    return keep, {"new": len(rows), "quarantined": q, "hubs": len(answered)}
