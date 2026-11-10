import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
def robots(host):
    try:
        r = requests.get(f"https://{host}/robots.txt", headers=UA, timeout=20); t = r.text if r.ok else ""
        dis = re.findall(r"(?im)^disallow:\s*(\S*)", t)[:8]; return f"robots {r.status_code} disallow={dis}"
    except Exception as e: return "robots ERR"
JOBS = [("commodity-board.com", "/category/oil-seeds/sesame", r"FOB|USD|EUR/kg|per ton"), ("commodity-board.com", "/chad-sesame-steady-but-firm-as-india-fob-values-edge-higher", r"FOB|USD/t|EUR"),
        ("afca.coffee", "/portfolio-item/tadesse-desta-import-and-export-company", r"Email|Phone|Tel|@"), ("afca.coffee", "/members/", r"portfolio-item"), ("afca.coffee", "/portfolio/", r"portfolio-item"),
        ("www.algrano.com", "/en/seller-profiles/16950-mulugeta-tsige-coffee-exporter?tab=about", r"FOB|price|Ethiopia"), ("www.algrano.com", "/en/seller-profiles", r"seller-profiles/\d+"),
        ("ammanchamber.org.jo", "/en/news/details/396903/list-of-major-ethiopian-coffee-exporters", r"@|Tel|PLC"), ("blueniletrade.com", "/prices/", r"USD|FOB|Sesame|\d{4}"),
        ("www.2merkato.com", "/news/capital-market-and-commodity-exchange/", r"Daily Trade Data"), ("ugandacoffee.go.ug", "/", r"report|Report"), ("ugandacoffee.go.ug", "/resource-center/monthly-reports", r"\.pdf"),
        ("apeda.gov.in", "/MarketIntelligence", r"\.pdf"), ("agriexchange.apeda.gov.in", "/MarketReport/Reports/", r"\.pdf"), ("www.africancashewalliance.com", "/en/news-and-info/cashew-news", r"price|FCFA|per kg"),
        ("cargolinked.com", "/directory/temerachi-coffee-export-b8f3456d", r"@|Phone"), ("www.marcopolis.net", "/top-coffee-exporters-in-ethiopia.htm", r"PLC|Coffee"),
        ("www.mundus-agri.eu", "/news/sesame-seeds-market-information.n1045.html", r"USD|EUR|FOB"), ("ricenewstoday.com", "/", r"USD|per ton|\$\d{3}"), ("www.ardb.com.kh", "/", r"pdf|price")]
seen = {}
for host, path, pat in JOBS:
    try:
        if host not in seen: seen[host] = robots(host)
        r = requests.get(f"https://{host}{path}", headers=UA, timeout=30); h = r.text; t = txt(h)
        hits = [t[max(0, m.start() - 90):m.start() + 210] for m in list(re.finditer(pat, t))[:2]]
        links = sorted(set(re.findall(r'href="([^"]*(?:portfolio-item|seller-profiles/\d|daily-trade-data|\.pdf|monthly-report)[^"]*)"', h, re.I)))
        print(f"== {host}{path[:60]} | {r.status_code} | {len(h)} | {seen[host]} | links {len(links)} {links[:4]}")
        for x in hits: print("     >", x)
    except Exception as e:
        print(f"== {host}{path[:50]} ERR {str(e)[:90]}")
