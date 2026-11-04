"""Source registry: every data source the system knows, with what it is, how it is reached and its real state.

Statuses (a directory entry is not a connector):
  discovered      listed in the research backlog only, nothing built
  access_pending  needs a key, registration or approval that is not in place
  implemented     code exists but is not scheduled (stale upstream, captcha, blocked)
  active          scheduled, and its last run returned data within its refresh window
  degraded        scheduled, but the last run failed, came back empty, or the data is older than allowed
  disabled        switched off on purpose

Writes data/registry/sources.json and data/registry/sources.csv. Run after leads.health:  python -m leads.registry
State comes from data/leads/health.json (tenders) and the files each collector writes; nothing here calls a source."""
import csv
import hashlib
import importlib
import json
import time

from .common import DATA, LEADS

OUT = DATA / "registry"

# Tender / procurement connectors that are scheduled (leads.yml LIGHT + HEAVY): module -> (geography, access)
TENDERS = {
    "ted": ("EU + EEA", "official API (TED Search)"), "fts": ("UK", "official API (Find a Tender OCDS)"),
    "sam": ("USA", "official API (SAM.gov, key)"), "canadabuys": ("Canada", "official open data"),
    "za": ("South Africa", "official API (eTenders OCDS)"), "worldbank": ("Global (World Bank)", "official API"),
    "ebrd": ("EBRD countries", "public notices page"), "mrgov": ("Israel", "public portal"),
    "ungm": ("Global (UN)", "public notices page"), "undp": ("Global (UNDP)", "public notices page"),
    "aiib": ("Asia (AIIB)", "public notices page"), "isdb": ("IsDB members", "public notices page"),
    "etimad": ("Saudi Arabia", "public search page"), "prozorro": ("Ukraine", "official API"),
    "pncp": ("Brazil", "official API (PNCP)"), "secop": ("Colombia", "official open data (Socrata)"),
    "germany": ("Germany", "official open data"), "contractsfinder": ("UK", "official API"),
    "paraguay": ("Paraguay", "official OCDS API"), "dominican": ("Dominican Republic", "official OCDS API"),
    "austender": ("Australia", "official OCDS API"), "oman": ("Oman", "public portal"), "france": ("France", "official open data (BOAMP)"),
    "spain": ("Spain", "official open data (PLACSP)"), "kenya": ("Kenya", "official API (PPIP)"),
    "moldova": ("Moldova", "official API (MTender)"), "uruguay": ("Uruguay", "official open data"),
    "bahrain": ("Bahrain", "public portal"), "malaysia": ("Malaysia", "public portal"), "qatar": ("Qatar", "public portal"),
    "israel": ("Israel", "public portals"), "nyc": ("USA (New York City)", "official open data"),
    "us_cities": ("USA (cities)", "official open data"), "wb_pipeline": ("Global (World Bank projects)", "official API"),
    "ocdr_tenders": ("~50 countries (OCDS registry)", "official bulk downloads"), "afdb": ("Africa (AfDB)", "public notices page"),
    "iadb": ("Latin America (IDB)", "public notices page"), "chile": ("Chile", "official API (Mercado Publico)"),
    "simap": ("Switzerland", "official API"), "gets": ("New Zealand", "public portal"), "india": ("India", "public portals (CPPP)"),
    "rwanda": ("Rwanda", "public portal (Umucyo)"), "uganda": ("Uganda", "public portal (eGP)"),
    "ghana": ("Ghana", "public portal (GHANEPS)"), "malawi": ("Malawi", "public portal (PPDA)"),
    "mozambique": ("Mozambique", "public portal (UFSA)"), "dubai": ("UAE (Dubai)", "public portal (eSupply)"),
    "philippines": ("Philippines", "public portal (PhilGEPS)"),
}
# Built but not scheduled, with the reason
IMPLEMENTED = {"zambia": ("Zambia", "public portal (ZPPA)", "list page needs a captcha"),
               "tanzania": ("Tanzania", "official OCDS API (NeST)", "upstream data months late"),
               "georgia": ("Georgia", "official API", "not scheduled"), "ecuador": ("Ecuador", "official OCDS API", "not scheduled")}
# Supplier, market and signal sources (not tenders): module -> (track, what, access, output file to date-check)
OTHER = {
    "awards": ("suppliers", "award notices from all tender sources", "derived", "leads/awards.csv"),
    "ext_awards": ("suppliers", "World Bank contract awards, USAspending", "official APIs", None),
    "importyeti": ("suppliers", "US customs bills of lading by HS heading (foreign exporters)", "public web pages", "leads/importyeti_state.json"),
    "wikidata_companies": ("suppliers", "notable producers and traders", "official SPARQL", None),
    "listed_companies": ("suppliers", "listed companies", "official SPARQL", None),
    "commodity_producers": ("suppliers", "commodity producers by product", "official SPARQL", None),
    "web_contacts": ("suppliers", "official contact details from company sites", "public web pages", None),
    "sanctions": ("compliance", "OFAC, EU, UN, UK sanctions lists", "official downloads", "leads/sanctions.json"),
    "integrity": ("compliance", "country governance and integrity indicators", "official open data", "leads/governance.csv"),
    "markets": ("commodities", "trade flows and buyer prices (UN Comtrade and others)", "official APIs", "leads/markets.csv"),
    "price_trends": ("commodities", "commodity price trends", "World Bank Pink Sheet (monthly, CC BY 4.0) + Commodities Tracker", "leads/price_trends.csv"),
    "trends": ("signals", "Google Trends interest by country (pytrends, unofficial library; official API is alpha, access requested)",
               "unofficial library", "leads/trends.csv"),
    "grants": ("projects", "grants and incentives", "public pages", "leads/grants.csv"),
    "news": ("signals", "economic news", "public RSS", None),
    "wb_plans": ("projects", "World Bank procurement plans (documents API) and IPF contract awards (Finances One DS00005, CC BY 4.0)", "official APIs", "leads/wb_plans.csv"),
    "lei": ("suppliers", "company groups and ultimate parents (GLEIF LEI register)", "official API", "leads/groups_lei.csv"),
    "fx": ("commodities", "exchange rates, USD per unit (ECB reference rates)", "official API", "leads/fx.csv"),
    "briefing": ("signals", "world briefing feed: trade, shipping, commodities, geopolitics, regional infrastructure, owner's own feeds (Briefing Sources tab)", "public RSS feeds", "leads/briefing_items.csv"),
    "gdelt": ("signals", "business news per watched country (GDELT DOC API, free, no key)", "official API", "leads/news.csv"),
    "plays": ("brain", "deal theses from signals: supply the winner, arbitrage gap, pre-tender approach", "derived", "leads/plays.csv"),
    "dealfit": ("brain", "deal-fit ranking with why and flags per notice", "derived", "leads/supplier_sectors.csv"),
}
# Research backlog from the upgrade brief (2026-11-04): id -> (name, url, track, mapped module or "")
BACKLOG = {
    "S01": ("AMIS Market Monitor", "https://www.amis-outlook.org/market-monitor", "commodities", ""),
    "S02": ("USDA FAS Open Data", "https://apps.fas.usda.gov/opendataweb/home", "commodities", ""),
    "S03": ("FAO GIEWS / FPMA", "https://www.fao.org/giews/food-prices/price-tool/en/", "commodities", ""),
    "S04": ("World Bank Commodity Markets", "https://www.worldbank.org/en/research/commodity-markets", "commodities", "price_trends"),
    "S05": ("CONAB", "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-graos", "commodities", ""),
    "S06": ("MPOB", "https://bepi.mpob.gov.my/", "commodities", ""),
    "S07": ("USGS Mineral Commodity Summaries", "https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries/", "commodities", ""),
    "S08": ("EIA Open Data", "https://www.eia.gov/opendata/", "commodities", ""),
    "S09": ("UN Comtrade", "https://uncomtrade.org/docs/subscriptions/", "commodities", "markets"),
    "S10": ("FAOSTAT", "https://www.fao.org/faostat/", "commodities", ""),
    "S11": ("Eurostat", "https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-introduction", "commodities", ""),
    "S12": ("World Bank Opportunities", "https://projects.worldbank.org/en/projects-operations/opportunities", "projects", "worldbank"),
    "S13": ("ADB Project Procurement", "https://www.adb.org/business/project-procurement/business-opportunities", "projects", ""),
    "S14": ("AIIB Project Procurement", "https://www.aiib.org/en/opportunities/business/project-procurement/list.html", "projects", "aiib"),
    "S15": ("AfDB Procurement", "https://www.afdb.org/en/projects-and-operations/procurement", "projects", "afdb"),
    "S16": ("IDB Procurement Plans", "https://www.iadb.org/en/how-we-can-work-together/procurement/procurement-projects/procurement-plans", "projects", "iadb"),
    "S17": ("IFC Disclosures", "https://disclosures.ifc.org/", "projects", ""),
    "S18": ("Etimad", "https://tenders.etimad.sa/Tender/", "projects", "etimad"),
    "S19": ("GeBIZ", "https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml", "projects", ""),
    "S20": ("GeM Global Tender Enquiry", "https://bidplus-global.gem.gov.in/", "projects", ""),
    "S21": ("India eProcurement", "https://www.etenders.gov.in/", "projects", "india"),
    "S22": ("China Government Procurement", "https://www.ccgp.gov.cn/", "projects", ""),
    "S23": ("MOFCOM China International Bidding", "https://chinabidding.mofcom.gov.cn/", "projects", ""),
    "S24": ("Kenya PPIP", "https://www.tenders.go.ke/", "projects", "kenya"),
    "S25": ("South Africa eTenders", "https://www.etenders.gov.za/Home/Opportunities", "projects", "za"),
    "S26": ("Brazil PNCP Open Data", "https://www.gov.br/pncp/pt-br/acesso-a-informacao/dados-abertos", "projects", "pncp"),
    "S27": ("ChileCompra API", "https://www.chilecompra.cl/api/", "projects", "chile"),
    "S28": ("TED Search API", "https://docs.ted.europa.eu/api/latest/search.html", "projects", "ted"),
    "S29": ("HKTDC Sourcing", "https://sourcing.hktdc.com/en", "suppliers", ""),
    "S30": ("buyKOREA / KOTRA", "https://www.kotra.or.kr/english/subList/41000046004", "suppliers", ""),
    "S31": ("Taiwantrade / TAITRA", "https://www-onepage.taiwantrade.com/mp/services", "suppliers", ""),
    "S32": ("Canton Fair", "https://www.cantonfair.org.cn/en/index.html", "suppliers", ""),
    "S33": ("ProColombia B2B", "https://b2bmarketplace.procolombia.co/es", "suppliers", ""),
    "S34": ("Sri Lanka Export Development Board", "https://www.srilankabusiness.com/exporters/", "suppliers", ""),
    "S35": ("FPEF Exporter Members", "https://www.fpef.co.za/exportermembersextensivelist", "suppliers", ""),
    "S36": ("GLEIF", "https://www.gleif.org/en/lei-data/access-and-use-lei-data", "suppliers", ""),
    "S37": ("GDELT", "https://gdeltproject.org/data.html", "signals", ""),
    "S38": ("Google Trends API", "https://developers.google.com/search/apis/trends", "signals", "trends"),
    "S39": ("Wikimedia Analytics", "https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/getting-started.html", "signals", ""),
    "S40": ("ACWA Projects", "https://acwapower.com/en/what-we-do/projects/", "projects", ""),
    "S41": ("Equinix Expansions", "https://www.equinix.com/data-centers/expansions", "projects", ""),
    "S42": ("POWERCHINA Procurement", "https://bid.powerchina.cn/", "projects", ""),
}
MAX_AGE_H = 30  # a scheduled tender source older than this is degraded


def _doc(mod):
    try:
        m = importlib.import_module(f"leads.{mod}")
        return ((m.__doc__ or "").strip().splitlines() or [""])[0][:200]
    except Exception as e:  # noqa: BLE001
        return f"(module not loadable: {type(e).__name__})"


def _ver(mod):
    p = LEADS.parent.parent / "leads" / f"{mod}.py"
    p = p if p.exists() else (DATA.parent / "leads" / f"{mod}.py")
    return hashlib.sha1(p.read_bytes()).hexdigest()[:8] if p.exists() else ""


def build():
    now = time.time()
    health = {}
    hp = LEADS / "health.json"
    if hp.exists():
        health = {s["source"]: s for s in json.loads(hp.read_text()).get("sources", [])}
    rows = []
    for mod, (geo, access) in TENDERS.items():
        h = health.get(mod)
        if not h:
            status, note = "degraded", "no health record yet"
        elif h.get("flags"):
            status, note = "degraded", "; ".join(h["flags"])
        elif (h.get("age_h") or 0) > MAX_AGE_H:
            status, note = "degraded", f"data {h['age_h']} h old"
        else:
            status, note = "active", ""
        rows.append({"id": mod, "name": _doc(mod), "track": "projects", "kind": "tenders", "geography": geo, "access": access,
                     "status": status, "rows": (h or {}).get("rows", ""), "age_h": (h or {}).get("age_h", ""), "note": note,
                     "refresh": "every 2 h" if mod not in ("bahrain", "nyc", "us_cities", "za", "chile", "india", "germany", "paraguay",
                                                         "dominican", "france", "spain", "wb_pipeline", "worldbank", "mrgov") else "twice a day",
                     "parser_version": _ver(mod), "cost": "free", "url": ""})
    for mod, (geo, access, why) in IMPLEMENTED.items():
        rows.append({"id": mod, "name": _doc(mod), "track": "projects", "kind": "tenders", "geography": geo, "access": access,
                     "status": "implemented", "rows": "", "age_h": "", "note": why, "refresh": "not scheduled",
                     "parser_version": _ver(mod), "cost": "free", "url": ""})
    for mod, (track, what, access, out) in OTHER.items():
        p = DATA / out if out else None
        age = round((now - p.stat().st_mtime) / 3600, 1) if p and p.exists() else ""
        status = "active" if age != "" and age < 24 * 8 else ("degraded" if out else "active")
        if mod == "trends":
            note = "unofficial library; the official Google Trends API is restricted alpha (access requested, not granted)"
        else:
            note = "" if status == "active" else "output file missing or older than 8 days"
        rows.append({"id": mod, "name": what, "track": track, "kind": track, "geography": "global", "access": access,
                     "status": status, "rows": "", "age_h": age, "note": note, "refresh": "daily to weekly",
                     "parser_version": _ver(mod), "cost": "free", "url": ""})
    known = {r["id"] for r in rows}
    for sid, (name, url, track, mapped) in BACKLOG.items():
        if mapped and mapped in known:
            st = next(r["status"] for r in rows if r["id"] == mapped)
            rows.append({"id": sid, "name": name, "track": track, "kind": "backlog", "geography": "", "access": "",
                         "status": st, "rows": "", "age_h": "", "note": f"covered by connector '{mapped}'", "refresh": "",
                         "parser_version": "", "cost": "", "url": url})
        else:
            rows.append({"id": sid, "name": name, "track": track, "kind": "backlog", "geography": "", "access": "unverified",
                         "status": "discovered", "rows": "", "age_h": "", "note": "researched link only: access, terms and cost not verified",
                         "refresh": "", "parser_version": "", "cost": "unverified", "url": url})
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    (OUT / "sources.json").write_text(json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "summary": summary,
                                                  "sources": rows}, indent=1, ensure_ascii=False))
    with open(OUT / "sources.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("registry", summary)
    return rows


if __name__ == "__main__":
    build()
