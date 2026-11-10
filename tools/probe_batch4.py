"""World sweep, batch 4: Europe/Mediterranean, Central Asia, Caribbean, Oceania, plus exporter registries."""
import re, requests
from urllib import robotparser
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
CANDIDATES = [
    # Mediterranean olive oil, nuts, dried fruit, citrus
    ("poolred", "https://www.poolred.com/"),
    ("infaoliva", "https://www.infaoliva.com/precios/"),
    ("ismea", "https://www.ismeamercati.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/1"),
    ("borsa_bari", "https://www.borsamercibari.it/"),
    ("agrodata_ma", "https://www.agrimaroc.ma/"),
    ("tunisia_onh", "http://www.onh.com.tn/"),
    ("tr_ziraat_odasi", "https://www.tzob.org.tr/"),
    ("tr_izmir_tb", "https://www.itb.org.tr/"),
    ("gr_eleo", "https://www.minagric.gr/"),
    ("hazelnut_tr", "https://www.fiskobirlik.com.tr/"),
    ("fiskobirlik_price", "https://www.giresunticaretborsasi.org.tr/"),
    ("es_mapa", "https://www.mapa.gob.es/es/estadistica/temas/estadisticas-agrarias/economia/precios-percibidos-pagados-salarios/"),
    ("fr_franceagrimer", "https://www.franceagrimer.fr/"),
    ("rnm_fr", "https://rnm.franceagrimer.fr/prix"),
    ("lombardia_borse", "https://www.borsamerci.it/"),
    ("bmti", "https://www.bmti.it/"),
    ("pl_zsrir", "https://www.gov.pl/web/rolnictwo/zintegrowany-system-rolniczej-informacji-rynkowej"),
    ("de_ble", "https://www.ble.de/DE/BZL/Daten-Berichte/Preise/preise_node.html"),
    ("uk_ahdb_grain", "https://ahdb.org.uk/cereals-oilseeds/cereals-and-oilseeds-markets"),
    ("nl_agrimatie", "https://agrimatie.nl/"),
    ("dk_lf", "https://lf.dk/"),
    # Central Asia / Caucasus / Russia-Ukraine
    ("uz_uzex", "https://uzex.uz/"),
    ("kz_grain", "https://www.kazakh-zerno.kz/"),
    ("uz_agro", "https://agro.uz/"),
    ("ge_mepa", "https://mepa.gov.ge/"),
    ("ua_apk", "https://www.apk-inform.com/en/prices"),
    ("ua_latif", "https://latifundist.com/en/"),
    ("ru_ikar", "https://ikar.ru/eng/"),
    ("ru_zerno", "https://zol.ru/"),
    # Caribbean / Central America
    ("do_cacao", "https://www.conacado.com.do/"),
    ("do_minagri", "https://agricultura.gob.do/precios/"),
    ("jm_coffee", "https://jacra.org/"),
    ("gt_bolsa", "https://www.bolsaagricola.gt/"),
    ("hn_sag", "https://www.sag.gob.hn/"),
    ("ni_mag", "https://www.mag.gob.ni/"),
    ("cr_cnp", "https://www.cnp.go.cr/"),
    ("pa_ima", "https://www.ima.gob.pa/"),
    ("mx_sniim", "http://www.economia-sniim.gob.mx/nuevo/"),
    ("mx_sniim2", "https://www.economia-sniim.gob.mx/SNIIM-Agricola/"),
    ("mx_amecafe", "https://amecafe.org.mx/"),
    # Oceania / Pacific
    ("nz_ag", "https://www.mpi.govt.nz/"),
    ("au_abares", "https://www.agriculture.gov.au/abares/research-topics/agricultural-outlook/data"),
    ("au_grainc", "https://www.graincentral.com/"),
    ("fj_mof", "https://www.agriculture.gov.fj/"),
    ("vu_vcmb", "https://vcmb.vu/"),
    ("sb_cema", "https://www.cema.com.sb/"),
    ("png_cic", "https://www.coffeecorp.org.pg/"),
    ("png_kik", "https://www.kik.com.pg/"),
    ("png_cocoaboard", "https://www.cocoaboard.org.pg/"),
    # exporter registries worldwide
    ("gh_cocobod_lbc", "https://cocobod.gh/resources"),
    ("ci_ccc_exp", "https://www.conseilcafecacao.ci/index.php?option=com_content&view=article&id=102"),
    ("rw_naeb_exp", "https://www.naeb.gov.rw/exports"),
    ("rw_naeb_dir", "https://www.naeb.gov.rw/index.php?id=50"),
    ("ke_tbk", "https://www.teaboard.or.ke/"),
    ("tz_tbt", "https://www.teaboard.or.tz/"),
    ("in_apeda_exp", "https://apeda.gov.in/apedawebsite/"),
    ("in_coffeeboard", "https://coffeeboard.gov.in/"),
    ("in_coffeeboard_exp", "https://coffeeboard.gov.in/Database/Exporters.html"),
    ("in_cashew_cepci", "https://cashewindia.org/"),
    ("lk_edb", "https://www.srilankabusiness.com/exporters-directory/"),
    ("lk_edb2", "https://www.srilankabusiness.com/find-sri-lankan-suppliers/"),
    ("vn_vicofa", "https://vicofa.org.vn/"),
    ("id_aeki", "https://www.aeki-aice.org/"),
    ("id_gapki", "https://gapki.id/"),
    ("br_cecafe", "https://www.cecafe.com.br/"),
    ("co_fnc_exp", "https://federaciondecafeteros.org/wp/exportadores/"),
    ("pe_adex", "https://www.adexperu.org.pe/"),
    ("pe_promperu", "https://www.perumarketplace.com/"),
    ("ec_fedexpor", "https://www.fedexpor.com/"),
    ("ar_ciara", "https://www.ciaracec.com.ar/"),
    ("py_capeco", "https://capeco.org.py/"),
    ("eg_aec", "https://www.aecegypt.com/"),
    ("ma_morocco_foodex", "https://www.morocco-foodex.org.ma/"),
    ("tr_turkishexporters", "https://www.turkishexporter.net/"),
    ("tr_tim", "https://tim.org.tr/en/"),
    ("za_fpef", "https://www.fpef.co.za/"),
    ("za_citrus", "https://www.cga.co.za/"),
    ("za_safex", "https://www.jse.co.za/our-business/commodity-derivatives-market"),
    ("ng_cocoa_assoc", "https://can.org.ng/"),
    ("et_ecta", "https://www.ethiopiancoffeetea.gov.et/"),
    ("gh_gepa", "https://www.gepaghana.org/"),
    ("ke_epc", "https://www.epzakenya.com/"),
    ("tz_tantrade", "https://www.tantrade.go.tz/"),
    ("ug_ueipb", "https://www.ugandaexports.go.ug/"),
    ("sn_asepex", "https://asepex.sn/"),
    ("mg_vanilla", "https://www.edbm.mg/"),
    ("ir_tpo", "https://en.tpo.ir/"),
    ("pk_tdap", "https://tdap.gov.pk/"),
    ("bd_epb", "http://epb.gov.bd/"),
    ("mm_myantrade", "https://www.myantrade.gov.mm/"),
    ("kh_cambodia_rice", "https://crf.org.kh/"),
    ("th_ditp", "https://www.ditp.go.th/"),
    ("ph_dti", "https://tradelinephilippines.dti.gov.ph/"),
    ("my_matrade", "https://www.matrade.gov.my/en/malaysian-exporters/directory"),
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
        r = requests.get(url, headers=UA, timeout=(10, 20), allow_redirects=True, stream=True)
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
