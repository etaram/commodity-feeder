"""Wide probe of national tender portals: reachable? fresh (deadlines in the coming weeks)? Saves each page."""
import os, re, sys, datetime as dt
sys.path.insert(0, ".")
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as cr
os.makedirs("data/probe/portals2", exist_ok=True)
U = {
 # Africa
 "gh_ghaneps_ct": "https://www.ghaneps.gov.gh/epps/quickSearchAction.do?searchSelect=1&selectedItem=quickSearchAction.do%3FsearchSelect%3D1",
 "gh_ghaneps_list": "https://www.ghaneps.gov.gh/epps/viewCFTSAction.do?latest=true",
 "tz_nest_pub": "https://nest.go.tz/tenders/published",
 "tz_nest_api": "https://nest.go.tz/gateway/nest-tendering-api/api/public/tenders?page=0&size=20",
 "zm_zppa": "https://eprocure.zppa.org.zm/epps/viewCFTSAction.do?latest=true",
 "mw_ppda": "https://www.ppda.mw/tenders",
 "bw_ppadb": "https://www.ppadb.co.bw/tenders",
 "na_cpb": "https://eprocurement.cpb.org.na/",
 "zw_praz": "https://egp.praz.org.zw/",
 "ng_nocopo": "https://nocopo.bpp.gov.ng/",
 "ng_etenders": "https://www.etenders.com.ng/",
 "cm_armp": "https://www.armp.cm/",
 "cm_marches": "https://marchespublics.cm/",
 "bj_marches": "https://marches-publics.bj/",
 "tg_marches": "https://marchespublics.gouv.tg/",
 "bf_dgcmef": "https://www.dgcmef.gov.bf/fr/appels-offres",
 "mu_procure": "https://publicprocurement.govmu.org/",
 "mu_eproc": "https://eproc.govmu.org/",
 "mg_armp": "https://www.armp.mg/",
 "cd_armp": "https://www.armp-rdc.org/",
 "ml_dgmp": "https://www.dgmp.gouv.ml/",
 "sl_ppa": "https://www.nppa.gov.sl/",
 "so_mof": "https://mof.gov.so/procurement",
 "dj_marches": "https://www.marches-publics.dj/",
 "ao_compras": "https://www.compraspublicas.gv.ao/",
 "mz_ufsa": "https://www.ufsa.gov.mz/",
 "sd_none": "https://www.tenders.gov.sd/",
 # MENA
 "jo_gtd": "https://www.gtd.gov.jo/",
 "jo_jonepps": "https://jonepps.gov.jo/",
 "ae_dubai": "https://esupply.dubai.gov.ae/esop/guest/go/public/opportunity/current",
 "ae_ad": "https://www.adgpg.gov.ae/",
 "kw_capt": "https://capt.gov.kw/en/tenders/opening-tenders/",
 "tn_tuneps": "https://www.tuneps.tn/",
 "iq_mop": "https://mop.gov.iq/",
 "ps_shiraa": "https://www.shiraa.gov.ps/",
 "lb_ppa": "https://ppa.gov.lb/",
 # Asia
 "ph_philgeps": "https://notices.philgeps.gov.ph/GEPSNONPILOT/Tender/SplashOpportunitiesSearchUI.aspx?menuIndex=3&ClickFrom=OpenOpp&Result=3",
 "id_inaproc": "https://spse.inaproc.id/",
 "id_lpse": "https://lpse.lkpp.go.id/eproc4/lelang",
 "vn_muasamcong": "https://muasamcong.mpi.gov.vn/",
 "bd_egp": "https://www.eprocure.gov.bd/resources/common/AllTenders.jsp",
 "pk_ppra": "https://www.ppra.org.pk/dad_tenders.asp",
 "pk_epads": "https://eprocure.gov.pk/#/supplier/opportunities",
 "lk_promise": "https://www.promise.lk/",
 "np_bolpatra": "https://bolpatra.gov.np/egp/searchOpportunity",
 "kz_goszakup": "https://goszakup.gov.kz/ru/search/announce",
 "uz_xarid": "https://xarid.uzex.uz/",
 "ge_spa": "https://tenders.procurement.gov.ge/public/?lang=en",
 "am_armeps": "https://armeps.am/epps/viewCFTSAction.do?latest=true",
 "mn_tender": "https://www.tender.gov.mn/",
 "kh_gdpp": "https://gdpp.gov.kh/",
 "th_gprocurement": "https://process3.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch",
 # Latin America (live OCDS APIs)
 "ec_sercop": "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds?year=2026&page=1",
 "pa_panamacompra": "https://ocds.panamacompraencifras.gob.pa/",
 "hn_oncae": "https://contratacionesabiertas.gob.hn/api/v1/release/?format=json",
 "gt_guatecompras": "https://www.guatecompras.gt/concursos/consultaConcursos.aspx",
 "pe_seace": "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml",
 "mx_comprasmx": "https://comprasmx.buengobierno.gob.mx/",
 "cr_sicop": "https://www.sicop.go.cr/",
 "ar_comprar": "https://comprar.gob.ar/Compras.aspx?qs=W1HXHGHtH10=",
 "sv_comprasal": "https://www.comprasal.gob.sv/",
 "bo_sicoes": "https://www.sicoes.gob.bo/",
}
today = dt.date.today()
soon = {(today + dt.timedelta(days=d)) for d in range(1, 60)}
pats = set()
for d in soon:
    pats |= {d.strftime("%d/%m/%Y"), d.isoformat(), d.strftime("%d-%m-%Y"), d.strftime("%d.%m.%Y"), d.strftime("%d %b %Y"), d.strftime("%b %d, %Y")}
def go(kv):
    k, u = kv
    try:
        s = cr.Session(impersonate="chrome")
        r = s.get(u, timeout=35)
        t = r.text
        open(f"data/probe/portals2/{k}.html", "w", encoding="utf-8").write(t[:500000])
        ti = re.search(r"<title>(.*?)</title>", t, re.S | re.I)
        fresh = sum(t.count(p) for p in pats)
        return f"{k}\t{r.status_code}\t{len(t)}\tfresh={fresh}\t{(ti.group(1).strip()[:60] if ti else '')}\t{r.url[:80]}"
    except Exception as e:
        return f"{k}\tERR\t{str(e)[:110]}"
with ThreadPoolExecutor(12) as ex:
    for line in ex.map(go, U.items()):
        print(line, flush=True)
