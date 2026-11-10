import re, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "en"}
URLS = ["https://organic.ams.usda.gov/integrity/Reports/DataHistory", "https://organic.ams.usda.gov/integrity/", "https://organic.ams.usda.gov/integrity/Reports/Reports",
        "https://www.flocert.net/about-flocert/customer-search/", "https://ugandacoffee.go.ug/registered-exporters", "https://ugandacoffee.go.ug/",
        "https://apeda.gov.in/apedawebsite/Exporters_Directory/exporters_directory.htm", "https://agriexchange.apeda.gov.in/", "https://www.indiacoffee.org/coffee-exporters.html",
        "https://www.rainforest-alliance.org/business/certification/certificate-search-and-public-summaries/", "https://www.teaboard.gov.in/TEABOARDCSM/NQ==",
        "https://www.vicofa.org.vn/", "https://www.kenyacoffee.go.ke/", "https://royalcoffee.com/collections/all-coffees/products.json?limit=5",
        "https://www.globalgap.org/what-we-offer/ggn-label/", "https://www.sedex.com/", "https://ec.europa.eu/agriculture/ofis_public/actor_cbr/ctrl_actor_cbr.cfm"]
for u in URLS:
    try:
        r = requests.get(u, headers=UA, timeout=30)
        t = r.text
        files = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip)[^"]*)"', t, re.I)))[:6]
        title = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
        print(r.status_code, len(r.content), "|", u[:80], "|", (re.sub(r"\s+", " ", title.group(1))[:60] if title else ""), "| files", files)
        if "DataHistory" in u or "Reports/Reports" in u:
            for m in list(re.finditer(r'href="([^"]+)"[^>]*>([^<]{4,80})<', t))[:400]:
                if re.search(r"download|export|xls|csv|histor|operation", m.group(1) + m.group(2), re.I): print("   LINK", m.group(1)[:140], "|", m.group(2).strip()[:60])
        if "products.json" in u and r.ok:
            p = r.json()["products"][0]; print("   keys", list(p.keys()), "| vendor", p.get("vendor"), "| tags", p.get("tags")[:12] if isinstance(p.get("tags"), list) else p.get("tags"), "| body", re.sub(r"<[^>]+>", " ", p.get("body_html") or "")[:400])
    except Exception as e:
        print("ERR", u[:80], str(e)[:100])
