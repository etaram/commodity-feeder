import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
def robots(host):
    try:
        r = requests.get(f"https://{host}/robots.txt", headers=UA, timeout=20); t = r.text if r.ok else ""
        return f"robots {r.status_code} dis={re.findall(r'(?im)^disallow:\s*(\S*)', t)[:6]}"
    except Exception: return "robots ERR"
JOBS = [("globaledge.msu.edu", "/global-resources/resource/1316", r"Exporter|directory"), ("globaledge.msu.edu", "/countries/thailand/resources", r"Directory|Exporter"),
        ("globaledge.msu.edu", "/global-resources/trade-leads", r"Directory"), ("globaledge.msu.edu", "/globalresources/resourcesbytag/export-promotion-agency", r"Agency|Export"),
        ("www.sunsirs.com", "/uk/sectors-14.html", r"\d+\.\d\d"), ("www.sunsirs.com", "/CommodityPrice.html", r"\d+\.\d\d"), ("www.sunsirs.com", "/uk/", r"Commodity"),
        ("agriculture.gov.au", "/abares/data/weekly-commodity-price-update", r"xlsx|csv|US\$"), ("east-fruit.com", "/en/horticulture-market/prices/", r"\$|USD|price"),
        ("agro.gov.vn", "/vn/tID6392_Prices-of-agricultural-commodities-in-domestic-markets.html", r"VND|price|\d{2},\d{3}"), ("indianspices.com", "/marketing/price/domestic/daily-price.html", r"Rs|price|\d{3}"),
        ("www.tmx.co.tz", "/", r"results|Trade Results|\.pdf"), ("www.mansamarkets.com", "/commodities/sesame/nigeria", r"\$|NGN|per"), ("www.naeb.gov.rw", "/publications/news/last-week-export-performance", r"US\$|USD|Kg"),
        ("www.reap.com.pk", "/", r"member|Member"), ("ikar.ru", "/1/en/press/", r"\$|FOB"), ("www.gcx.com.gh", "/", r"price|GHS"), ("cocobod.gh", "/", r"price|Price"),
        ("www.anecacao.com", "/", r"export|socios"), ("www.promperu.gob.pe", "/", r"export"), ("www.acrop.app", "/mandi", r"₹|Rs|mandi"), ("www.cepici.gouv.ci", "/", r"export")]
seen = {}
for host, path, pat in JOBS:
    try:
        if host not in seen: seen[host] = robots(host)
        r = requests.get(f"https://{host}{path}", headers=UA, timeout=30); h = r.text; t = txt(h)
        hits = [t[max(0, m.start() - 120):m.start() + 260] for m in list(re.finditer(pat, t))[3:5]]
        files = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|pdf)[^"]*)"', h, re.I)))[:3]
        print(f"== {host}{path[:55]} | {r.status_code} | {len(h)} | {seen[host]} | tables {h.count('<table')} | files {files}")
        for x in hits: print("     >", x)
    except Exception as e:
        print(f"== {host}{path[:50]} ERR {str(e)[:80]}")
