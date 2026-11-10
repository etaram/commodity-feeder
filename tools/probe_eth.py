import re, requests, json
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
# 1. Mansa Markets: which commodities and countries, and is there a sitemap
for u in ["https://www.mansamarkets.com/sitemap.xml", "https://www.mansamarkets.com/commodities", "https://www.mansamarkets.com/commodities/sesame", "https://www.mansamarkets.com/commodities/sesame/nigeria"]:
    r = requests.get(u, headers=UA, timeout=40); h = r.text
    locs = re.findall(r"<loc>([^<]+)</loc>", h)
    print("==", u, r.status_code, len(h), "| locs", len(locs), locs[:6], "| links", sorted(set(re.findall(r'href="(/commodities/[^"?#]+)"', h)))[:30])
    if "nigeria" in u:
        t = txt(h); i = t.find("Price layers"); print("   LAYERS", t[i:i + 1500])
        print("   JSON", [m[:200] for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)][:2])
# 2. Spices Board daily price page structure
r = requests.get("https://indianspices.com/marketing/price/domestic/daily-price.html", headers=UA, timeout=40); h = r.text
t = txt(h); print("== spices", len(h)); 
for m in list(re.finditer(r"Spice: ([^|]+)\|", t))[:3]: print("   ", t[m.start():m.start() + 420])
print("   HTML", re.sub(r"\s+", " ", h[h.find("Spice:") - 600:h.find("Spice:") + 300]))
# 3. globalEDGE: country resource pages list (the seed for a per-country source hunt)
r = requests.get("https://globaledge.msu.edu/countries", headers=UA, timeout=40); h = r.text
cs = sorted(set(re.findall(r'href="(/countries/[a-z\-]+)"', h))); print("== globaledge countries", len(cs), cs[:8])
r = requests.get("https://globaledge.msu.edu/countries/ethiopia/resources", headers=UA, timeout=40); t = txt(r.text)
print("   ETH resources:", re.findall(r"\| ([^|]{4,80}?)&nbsp; \| open_in_new \| ([^|]{10,160})", t)[:12])
# 4. TMX results page
r = requests.get("https://www.tmx.co.tz/", headers=UA, timeout=40); h = r.text
print("== tmx links", sorted(set(re.findall(r'href="([^"]*(?:result|market|price|report)[^"]*)"', h, re.I)))[:15])
