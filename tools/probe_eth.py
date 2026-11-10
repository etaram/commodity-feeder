import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
def robots(host):
    try:
        r = requests.get(f"https://{host}/robots.txt", headers=UA, timeout=20); t = r.text if r.ok else ""
        return f"robots {r.status_code} dis={re.findall(r'(?im)^disallow:\s*(\S*)', t)[:5]}"
    except Exception: return "robots ERR"
JOBS = [("www.thairiceexporters.or.th", "/price%20the%20week.htm", r"US\$|USD|\d{3}"), ("www.thairiceexporters.or.th", "/List%20of%20Members.htm", r"Co\.|Ltd"), ("www.thairiceexporters.or.th", "/", r"member|price"),
        ("vietfood.org.vn", "/", r"price|member"), ("www.vinacas.com.vn", "/", r"member|hội viên"), ("peppervietnam.com", "/", r"price|giá"), ("www.vicofa.org.vn", "/", r"price"),
        ("www.cepea.org.br", "/en/indicator/coffee.aspx", r"\d+,\d\d|US\$"), ("www.cepea.org.br", "/en/indicator/soybean.aspx", r"\d+,\d\d|US\$"), ("www.cepea.org.br", "/en/indicator/sugar.aspx", r"\d+,\d\d"), ("www.cepea.org.br", "/en/indicator/cotton.aspx", r"\d+,\d\d"),
        ("www.bolsadecereales.com", "/", r"precio|FOB"), ("www.bcr.com.ar", "/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-locales-0", r"\$|precio"), ("www.magyp.gob.ar", "/sitio/areas/ss_mercados_agropecuarios/precios/", r"FOB|precio"),
        ("federaciondecafeteros.org", "/wp/estadisticas-cafeteras/", r"precio|xlsx"), ("www.ihcafe.hn", "/", r"precio"), ("www.anacafe.org", "/", r"precio"), ("www.anecacao.com", "/estadisticas/", r"precio|export"),
        ("ikar.ru", "/1/en/", r"FOB|\$/t"), ("www.apk-inform.com", "/en/prices", r"FOB|\$"), ("latifundist.com", "/en/novosti", r"FOB|USD"), ("www.zol.com.ua", "/en/", r"USD|price"),
        ("www.mpob.gov.my", "/", r"price|RM"), ("bepi.mpob.gov.my", "/index.php/en/", r"price|RM"), ("www.sunsirs.com", "/uk/prodetail-", r"\d"), ("www.100ppi.com", "/", r"价格|Price"),
        ("agmarknet.gov.in", "/", r"price|Price"), ("www.data.gov.in", "/resource/current-daily-price-various-commodities-various-markets-mandi", r"api|API"),
        ("www.gdt.co.nz", "/results", r"USD|\$"), ("www.globaldairytrade.info", "/en/product-results/", r"USD|\$"), ("www.agriculture.gov.au", "/abares/data/weekly-commodity-price-update", r"xlsx|US\$"),
        ("www.ams.usda.gov", "/market-news", r"report|Report"), ("mymarketnews.ams.usda.gov", "/", r"api|API|report"), ("www.exportsouthafrica.com", "/", r"exporter"), ("www.kenyacoffee.go.ke", "/", r"auction|price"),
        ("www.coffeedirectorate.go.ke", "/", r"auction|price"), ("eatta.co.ke", "/", r"auction|price"), ("www.tradeboard.co.ke", "/", r"price"), ("www.teaboard.gov.in", "/", r"auction|price")]
seen = {}
for host, path, pat in JOBS:
    try:
        if host not in seen: seen[host] = robots(host)
        r = requests.get(f"https://{host}{path}", headers=UA, timeout=25); h = r.text; t = txt(h)
        hits = [t[max(0, m.start() - 100):m.start() + 220] for m in list(re.finditer(pat, t))[2:4]]
        files = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|pdf)[^"]*)"', h, re.I)))[:3]
        print(f"== {host}{path[:50]} | {r.status_code} | {len(h)} | {seen[host]} | tables {h.count('<table')} | files {files}")
        for x in hits: print("     >", x)
    except Exception as e:
        print(f"== {host}{path[:50]} ERR {str(e)[:70]}")
