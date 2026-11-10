"""World sweep, batch 3: official boards, exchanges and registries per country.
Prints status, robots verdict, size and a text sample so adapters can be written."""
import re, requests, io
from urllib import robotparser
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
CANDIDATES = [
    # Latin America coffee/cocoa boards
    ("ihcafe", "https://www.ihcafe.hn/precios/"),
    ("anacafe", "https://www.anacafe.org/precios-del-cafe/"),
    ("icafe", "https://www.icafe.cr/sector-cafetalero/precios/"),
    ("icafe_liq", "https://www.icafe.cr/wp-content/uploads/informacion_mercado/precios/"),
    ("csc_sv", "https://www.csc.gob.sv/precios/"),
    ("fnc", "https://federaciondecafeteros.org/wp/estadisticas-cafeteras/"),
    ("fnc_precio", "https://federaciondecafeteros.org/wp/precio-del-cafe/"),
    ("anecacao", "https://anecacao.com/precio-referencial/"),
    ("anecacao2", "https://www.anecacao.com/index.php/es/precios.html"),
    ("midagri_sisap", "https://sistemas.midagri.gob.pe/sisap/"),
    ("midagri_precios", "https://www.gob.pe/institucion/midagri/informes-publicaciones?term=precios"),
    ("bcr_pizarra", "https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-locales-0"),
    ("bolsa_cereales", "https://www.bolsadecereales.com/precios-pizarra"),
    ("conab", "https://www.conab.gov.br/info-agro/precos"),
    ("cepea_cafe", "https://www.cepea.org.br/br/indicador/cafe.aspx"),
    ("odepa", "https://www.odepa.gob.cl/precios"),
    ("inia_uy", "https://www.mgap.gub.uy/unidad-organizativa/oficina-de-programacion-y-politicas-agropecuarias/precios"),
    # Africa
    ("cocobod", "https://cocobod.gh/"),
    ("ccc_ci", "https://www.conseilcafecacao.ci/"),
    ("naeb", "https://naeb.gov.rw/"),
    ("afa_ke", "https://www.afa.go.ke/"),
    ("nce_ke", "https://nairobicoffeeexchange.co.ke/"),
    ("ucda_rep", "https://ugandacoffee.go.ug/resources/reports"),
    ("zamace", "https://www.zamace.co.zm/"),
    ("ahcx", "https://ahcx.mw/"),
    ("bmm_mz", "https://www.bmm.co.mz/"),
    ("gum_sudan", "https://www.gumarabic.sd/"),
    ("sesame_eth", "https://www.ecx.com.et/"),
    ("ethiopia_eta", "https://ethiopiancoffee.gov.et/"),
    ("nigeria_nepc", "https://nepc.gov.ng/exporters-directory/"),
    ("tanzania_tcb", "https://www.coffeeboard.or.tz/"),
    ("tcb_auction", "https://www.coffeeboard.or.tz/auction-results/"),
    ("tzcashew", "https://www.cashew.go.tz/"),
    ("cashew_wb", "https://www.cashewinfo.com/"),
    # Asia
    ("colombo_tea", "https://web.forbestea.com/statistics/sri-lankan-statistics/90-weekly-tea-auction-quantities-averages/1299-sri-lanka-weekly-tea-auction-quantities-averages"),
    ("ceylon_brokers", "https://www.ceylonteabrokers.com/"),
    ("tea_board_lk", "https://www.srilankateaboard.lk/"),
    ("teaboard_in", "https://www.teaboard.gov.in/WEEKLYPRICES/2025"),
    ("teaboard_in2", "https://www.teaboard.gov.in/pdf/Weekly_Auction_Prices.pdf"),
    ("spices_in", "https://www.indianspices.com/marketing/price/domestic/daily-price.html"),
    ("agmarknet", "https://agmarknet.gov.in/"),
    ("psa_openstat", "https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2M__FG/0032M4AFP05.px/"),
    ("pca_ph", "https://pca.gov.ph/index.php/resources/market-prices"),
    ("kik_pg", "https://www.kik.com.pg/"),
    ("kemendag_hpe", "https://www.kemendag.go.id/berita/pengumuman?kategori=harga-patokan-ekspor"),
    ("bappebti", "https://bappebti.go.id/harga_komoditi"),
    ("mpob", "https://bepi.mpob.gov.my/index.php/en/"),
    ("vpsa", "https://peppervietnam.com/"),
    ("vinacas", "https://www.vinacas.com.vn/"),
    ("vfa_rice", "https://vietfood.org.vn/"),
    ("moit_rice", "https://moit.gov.vn/"),
    ("thai_rice", "https://www.thairiceexporters.or.th/default_eng.htm"),
    ("mrf_mm", "https://www.mrf.org.mm/"),
    ("pak_amis", "https://amis.pk/"),
    ("pak_rec", "https://www.reap.com.pk/"),
    ("iran_pistachio", "https://iranpistachio.org/"),
    ("tr_tmo", "https://www.tmo.gov.tr/"),
    ("tr_borsa", "https://www.izmirtb.org.tr/"),
    ("gdt", "https://www.globaldairytrade.info/en/product-results/"),
    ("abares", "https://www.agriculture.gov.au/abares/research-topics/agricultural-outlook/data"),
    # Black Sea
    ("ikar", "https://ikar.ru/eng/"),
    ("latifundist", "https://latifundist.com/en/"),
    ("apk_inform", "https://www.apk-inform.com/en/prices"),
    ("ukragro", "https://ukragroconsult.com/en/"),
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
        r = requests.get(url, headers=UA, timeout=25, allow_redirects=True)
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
        txt = re.sub(r"<[^>]+>", " ", txt); txt = re.sub(r"\s+", " ", txt)
        nums = len(re.findall(r"\b\d{2,5}[.,]\d{1,2}\b", txt))
        print(f"{name:14} {r.status_code} robots={ok} len={len(r.content):7} nums={nums:4} {r.url[:70]}")
        print("   ", txt[:260])
    except Exception as e:
        print(f"{name:14} ERR {type(e).__name__}: {str(e)[:120]}")
