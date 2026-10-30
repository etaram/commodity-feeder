import subprocess, sys, re, time, concurrent.futures as cf
def sh(c, t=900): return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
sh(f"{sys.executable} -m pip install -q 'scrapling[fetchers]'"); sh("scrapling install")
from scrapling.fetchers import Fetcher, StealthyFetcher
P = {
 "JPN japan p-portal": "https://www.p-portal.go.jp/pps-web-biz/UAB01/OAB0101",
 "KOR g2b": "https://www.g2b.go.kr/",
 "THA egp": "https://www.gprocurement.go.th/",
 "VNM muasamcong": "https://muasamcong.mpi.gov.vn/",
 "PHL philgeps": "https://notices.philgeps.gov.ph/GEPSNONPILOT/Tender/SplashOpenOpportunitiesUI.aspx?menuIndex=3&ClickFrom=OpenOpp&Result=3",
 "MYS myprocurement": "https://myprocurement.treasury.gov.my/",
 "BGD eprocure": "https://www.eprocure.gov.bd/",
 "PAK eprocure": "https://eprocure.gov.pk/",
 "LKA procurement": "https://www.nprocurement.gov.lk/",
 "NPL bolpatra": "https://bolpatra.gov.np/egp/",
 "KAZ goszakup": "https://goszakup.gov.kz/",
 "MNG tender": "https://www.tender.gov.mn/",
 "ARE uae": "https://www.mof.gov.ae/",
 "KWT capt": "https://www.capt.gov.kw/",
 "BHR tenderboard": "https://tenderboard.gov.bh/Tenders/Tenders",
 "JOR joneps": "https://portal.jordan.gov.jo/wps/portal/Home/JONEPS",
 "EGY etenders": "https://etenders.gov.eg/",
 "TUR ekap": "https://ekap.kik.gov.tr/",
 "NGA bpp": "https://www.bpp.gov.ng/",
 "GHA ppa": "https://www.ppa.gov.gh/",
 "TZA nest": "https://nest.go.tz/",
 "UGA gpp": "https://gpp.ppda.go.ug/",
 "ETH egp": "https://egp.ppa.gov.et/",
 "MAR marches": "https://www.marchespublics.gov.ma/",
 "TUN tuneps": "https://www.tuneps.tn/",
 "RWA umucyo": "https://www.umucyo.gov.rw/",
 "ZMB zppa": "https://www.zppa.org.zm/",
 "MEX comprasmx": "https://comprasmx.buengobierno.gob.mx/sitiopublico/#/",
 "PER seace": "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml",
 "ARG comprar": "https://comprar.gob.ar/BuscarAvanzado.aspx",
 "ECU sercop": "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/",
 "CRI sicop": "https://www.sicop.go.cr/",
 "PAN panamacompra": "https://www.panamacompra.gob.pa/",
 "URY compras": "https://www.comprasestatales.gub.uy/consultas/",
 "GTM guatecompras": "https://www.guatecompras.gt/",
 "HND honducompras": "https://www.honducompras.gob.hn/",
 "SRB portal": "https://portal.ujn.gov.rs/",
 "BIH ejn": "https://www.ejn.gov.ba/",
 "ALB app": "https://www.app.gov.al/",
 "MKD esjn": "https://www.e-nabavki.gov.mk/",
 "GEO tenders": "https://tenders.procurement.gov.ge/",
 "ARM gnumner": "https://www.gnumner.am/",
 "AZE etender": "https://etender.gov.az/",
 "MDA mtender": "https://mtender.gov.md/",
 "NOR doffin": "https://www.doffin.no/",
 "ISL utbod": "https://utbodsvefur.is/",
 "UZB xarid": "https://xarid.uz/",
 "TWN pcc": "https://web.pcc.gov.tw/",
 "IDN inaproc": "https://inaproc.id/",
 "SGP gebiz": "https://www.gebiz.gov.sg/",
 "HKG ctb": "https://www.gld.gov.hk/egazette/",
 "MUS cpb": "https://publicprocurement.govmu.org/",
 "NAM cpb": "https://www.cpb.com.na/",
 "BWA ppra": "https://www.ppra.org.bw/",
 "KEN tenders": "https://tenders.go.ke/",
 "SEN armp": "https://www.armp.sn/",
 "CIV dgmp": "https://www.dgmp.ci/",
}
def quick(item):
    k, u = item
    t0 = time.time()
    try:
        p = Fetcher.get(u, impersonate="chrome", timeout=25, verify=False)
        b = p.html_content if hasattr(p, "html_content") else str(p.body)
        return k, u, p.status, len(b), len(re.findall(r"tender|licita|appel d|ihale|招标|入札|จัดซื้อ|mua sắm|тендер", b, re.I)), "", time.time() - t0
    except Exception as e:
        return k, u, 0, 0, 0, type(e).__name__ + ":" + str(e)[:60].replace("\n", " "), time.time() - t0
with cf.ThreadPoolExecutor(10) as ex:
    res = list(ex.map(quick, P.items()))
print("== FETCHER ==", flush=True)
for k, u, st, ln, kw, err, dt in res: print(f"{k:22s} st={st} len={ln} kw={kw} {dt:.0f}s {err}", flush=True)
need = [(k, u) for k, u, st, ln, kw, err, dt in res if st in (403, 429, 503) or (st == 200 and ln < 3000) or ("Timeout" in err)]
print("== STEALTHY retries:", [k for k, _ in need], flush=True)
for k, u in need[:14]:
    t0 = time.time()
    try:
        p = StealthyFetcher.fetch(u, headless=True, network_idle=False, solve_cloudflare=True, timeout=60000)
        b = p.html_content
        print(f"{k:22s} STEALTHY st={p.status} len={len(b)} kw={len(re.findall('tender',b,re.I))} {time.time()-t0:.0f}s", flush=True)
    except Exception as e:
        print(f"{k:22s} STEALTHY ERR {str(e)[:70]!r}", flush=True)
