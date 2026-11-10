"""World sweep, batch 4: Europe/Mediterranean, Central Asia, Caribbean, Oceania, plus exporter registries."""
import re, requests
from urllib import robotparser
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
CANDIDATES = [
    # global and regional price boards
    ("fao_fpma", "https://fpma.fao.org/giews/fpmat4/#/dashboard/tool/international"),
    ("fao_fpma_api", "https://fpma.fao.org/giews/v4/price_module/api/v1/FpmaSerieInternational/"),
    ("fao_fpma_dom", "https://fpma.fao.org/giews/v4/price_module/api/v1/FpmaSerieDomestic/"),
    ("igc_prices", "https://www.igc.int/en/markets/marketinfo-prices.aspx"),
    ("igc_goi", "https://www.igc.int/en/markets/marketinfo-goi.aspx"),
    ("icco_daily", "https://www.icco.org/statistics/"),
    ("icco_home", "https://www.icco.org/"),
    ("ico_prices", "https://ico.org/resources/public-market-information/"),
    ("ipc_pepper", "https://www.ipcnet.org/"),
    ("ipc_prices", "https://www.ipcnet.org/price/"),
    ("icc_coconut", "https://coconutcommunity.org/page-statistics/weekly-price-update"),
    ("anrpc", "https://www.anrpc.org/"),
    ("lgm_rubber", "https://www.lgm.gov.my/webv2/dailyPrice"),
    ("raot", "https://www.raot.co.th/rubber2012/menu5.php"),
    ("mpob_daily", "https://bepi.mpob.gov.my/admin2/price_local_daily_view_cpo_msia.php"),
    ("mpoc", "https://mpoc.org.my/daily-palm-oil-price/"),
    ("cotlook", "https://www.cotlook.com/"),
    ("iso_sugar", "https://www.isosugar.org/prices.php"),
    ("ratin", "https://ratin.net/site/market"),
    ("ratin2", "https://www.ratin.net/"),
    ("sagis", "https://www.sagis.org.za/safex_historic.html"),
    ("sagis2", "https://www.sagis.org.za/"),
    ("afex", "https://afex.africa/"),
    ("gcx", "https://www.gcx.com.gh/market-data/"),
    ("kace", "https://www.kacekenya.co.ke/"),
    ("zamace", "https://www.zamace.co.zm/"),
    ("ahcx", "https://ahcx.mw/"),
    ("kalimati", "https://kalimatimarket.gov.np/price"),
    ("ncdex_spot", "https://www.ncdex.com/markets/spotprices"),
    ("enam", "https://enam.gov.in/web/dashboard/trade-data"),
    ("conab", "https://www.conab.gov.br/info-agro/precos"),
    ("uzex_quotes", "https://uzex.uz/en/Trade/WeeklyQuotes"),
    ("gdt_api", "https://www.globaldairytrade.info/umbraco/api/EventSummaryApi/GetEventSummary"),
    ("usda_gats", "https://www.fas.usda.gov/data"),
    ("imf_pcps", "https://www.imf.org/external/np/res/commod/External_Data.xls"),
    ("nut_inc", "https://inc.nutfruit.org/"),
    ("almond_board", "https://www.almonds.com/tools-and-resources/crop-reports/position-reports"),
    # exporter and member registries
    ("airea", "https://airea.net/members/"),
    ("airea2", "https://www.airea.net/list-of-members/"),
    ("apeda_dir", "https://agriexchange.apeda.gov.in/ExportersDirectory/exporters_list.aspx"),
    ("spices_exp", "https://www.indianspices.com/trade/exporters-directory.html"),
    ("cepci", "https://cashewindia.org/members-directory"),
    ("trea", "http://www.thairiceexporters.or.th/List_of_TREA_member.htm"),
    ("eatta_members", "https://www.eatta.co.ke/membership/members-directory"),
    ("eatta_api", "https://www.eatta.co.ke/api/members.php"),
    ("asoexport", "https://asoexport.org/afiliados/"),
    ("camcafe", "https://camcafeperu.com.pe/ES/asociados.php"),
    ("anecacao_soc", "https://anecacao.com/socios/"),
    ("adec_gt", "https://www.adecguatemala.com/"),
    ("uga_ua", "https://uga.ua/en/members/"),
    ("ukroliya", "https://www.ukroilprom.org.ua/en/members"),
    ("kib_tr", "https://www.kib.org.tr/en/members.html"),
    ("eib_tr", "https://www.eib.org.tr/en/"),
    ("gapki_member", "https://gapki.id/member/"),
    ("mpoa", "https://mpoa.org.my/members/"),
    ("vinacas_m", "https://www.vinacas.com.vn/hoi-vien"),
    ("gta_au", "https://www.graintrade.org.au/members"),
    ("pulse_au", "https://www.pulseaus.com.au/marketing/pulse-traders"),
    ("cscs_ca", "https://www.specialcrops.mb.ca/members"),
    ("pulse_ca", "https://pulsecanada.com/members"),
    ("gafta", "https://www.gafta.com/members"),
    ("fosfa", "https://www.fosfa.org/membership/members-list/"),
    ("globalshea", "https://globalshea.com/members"),
    ("esa_spice", "https://www.esa-spices.org/index-esa.html/members-esa.html"),
    ("spicecouncil_lk", "https://www.srilankanspices.com/members.html"),
    ("tea_lk", "https://teasrilanka.org/members"),
    ("cca_ci", "https://www.conseilcotonanacarde.ci/"),
    ("cashew_tz", "https://www.cashew.go.tz/exporters"),
    ("naspan", "https://nepc.gov.ng/"),
    ("unica_br", "https://unica.com.br/en/members/"),
    ("abiove", "https://abiove.org.br/en/associates/"),
    ("anec_br", "https://anec.com.br/en/members"),
    ("abpa_br", "https://abpa-br.org/associados/"),
    ("cec_ar", "https://www.ciaracec.com.ar/ciara/Asociados"),
    ("asoex_cl", "https://www.asoex.cl/socios.html"),
    ("chilenut", "https://www.chilenut.cl/socios/"),
    ("agap_pe", "https://agapperu.org/asociados/"),
    ("proecuador", "https://www.proecuador.gob.ec/directorio-de-exportadores/"),
    ("procolombia", "https://www.colombiatrade.com.co/"),
    ("coffee_ug_exp", "https://ugandacoffee.go.ug/registered-exporters"),
    ("sesame_ng", "https://naspan.org.ng/"),
    ("gh_cashew", "https://treecropsauthority.gov.gh/"),
]
def robots_ok(url):
    try:
        m = re.match(r"(https?://[^/]+)", url); rp = robotparser.RobotFileParser(m.group(1) + "/robots.txt")
        rp.read(); return rp.can_fetch(UA["User-Agent"], url)
    except Exception as e:
        return f"robots? {type(e).__name__}"
for name, url in CANDIDATES:
    try:
        ok = robots_ok(url)
        r = requests.get(url, headers=UA, timeout=(8, 15), allow_redirects=True, stream=True)
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > 2_000_000: break
        r.close(); text = body.decode(r.encoding or "utf-8", "replace")
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)
        txt = re.sub(r"<[^>]+>", " ", txt); txt = re.sub(r"\s+", " ", txt)
        nums = len(re.findall(r"\b\d{2,5}[.,]\d{1,2}\b", txt))
        print(f"{name:18} {r.status_code} robots={ok} len={len(body):7} nums={nums:4} {r.url[:70]}")
        print("    ", txt[:220])
    except Exception as e:
        print(f"{name:18} ERR {type(e).__name__}: {str(e)[:110]}")
