"""Probe candidate sources for Ethiopian coffee prices from the runner: direct, and through the regional relay."""
import re, requests
from leads.common import relay_get
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "en"}
URLS = ["https://www.ecx.com.et/", "http://www.ecx.com.et/", "https://www.ecx.com.et/Pages/MarketData.aspx", "https://ecta.gov.et/",
        "https://www.tridge.com/market-overview/coffee/ET", "https://www.tridge.com/intelligences/coffee-bean/ET/price",
        "https://www.genuineorigin.com/products.json?limit=250", "https://www.genuineorigin.com/collections/ethiopia/products.json",
        "https://www.sweetmarias.com/green-coffee.html?sm_country=Ethiopia", "https://royalcoffee.com/offerings/?country=ethiopia",
        "https://www.coffeebeancorral.com/categories/Green-Coffee-Beans/African-Green-Coffee-Beans/Ethiopia.aspx",
        "https://burmancoffee.com/product-category/green-coffee-beans/african-coffee/ethiopian/", "https://happymugcoffee.com/collections/green-coffee/products.json",
        "https://www.selinawamucii.com/insights/prices/ethiopia/coffee/", "https://t.me/s/ecx_official", "https://t.me/s/ECXEthiopia", "https://t.me/s/ethiopiancoffeeandteaauthority",
        "https://capitalethiopia.com/category/capital/", "https://algrano.com/en/coffee-market/ethiopia", "https://www.2merkato.com/news/capital-market-and-commodity-exchange/"]
def show(tag, status, text):
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)))
    hits = [t[max(0, m.start() - 60):m.start() + 160] for m in list(re.finditer(r"Sidam|Yirg|Guji|Feresula|per lb|/lb|USD/kg|Birr", t))[:3]]
    print(f"{tag} | {status} | {len(text)} | prices-like {len(re.findall(r'[$]\s?\d+[.]\d\d', t))} | {hits}")
for u in URLS:
    try:
        r = requests.get(u, headers=UA, timeout=30); show("direct " + u[:70], r.status_code, r.text)
        if "products.json" in u and r.ok:
            for p in r.json().get("products", [])[:400]:
                if re.search(r"ethiop|sidam|yirg|guji", p.get("title", "") + " " + " ".join(p.get("tags", []) if isinstance(p.get("tags"), list) else [str(p.get("tags"))]), re.I):
                    v = p["variants"][0]; print("   PRODUCT", p["title"][:70], "|", v.get("price"), v.get("title"), "| grams", v.get("grams"), "| updated", p.get("updated_at", "")[:10])
    except Exception as e:
        print("direct", u[:70], "ERR", str(e)[:90])
        try:
            rr = relay_get(u)
            if rr is not None: show("RELAY  " + u[:70], rr.status_code, rr.text)
            else: print("RELAY none")
        except Exception as e2: print("RELAY ERR", str(e2)[:90])
