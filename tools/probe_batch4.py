"""World sweep, batch 4: Europe/Mediterranean, Central Asia, Caribbean, Oceania, plus exporter registries."""
import re, requests
from urllib import robotparser
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
CANDIDATES = [
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
    # structure look at batch-4 hits
    ("ismea_prezzi", "https://www.ismeamercati.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/3523"),
    ("ke_tbk_prices", "https://www.teaboard.or.ke/"),
    ("in_coffee_auction", "https://coffeeboard.gov.in/Database/auction_prices.html"),
    ("in_coffee_mkt", "https://coffeeboard.gov.in/market-information"),
    ("id_aeki_members", "https://www.aeki-aice.org/anggota"),
    ("id_aeki_en", "https://www.aeki-aice.org/en/members"),
    ("id_gapki_harga", "https://gapki.id/harga-cpo"),
    ("png_cocoa_prices", "https://www.cocoaboard.org.pg/prices"),
    ("uzex_trades", "https://uzex.uz/en/trades"),
    ("mx_amecafe_precios", "https://amecafe.org.mx/precios/"),
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
