import re, requests, json
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
sm = requests.get("https://www.mansamarkets.com/sitemap.xml", headers=UA, timeout=40).text
locs = re.findall(r"<loc>([^<]+)</loc>", sm)
cc = [l for l in locs if re.search(r"/commodities/[a-z\-]+/[a-z\-]+$", l)]
print("mansa commodity/country pages", len(cc), cc[:12])
print("countries", sorted({l.split("/")[-1] for l in cc}))
r = requests.get("https://www.mansamarkets.com/commodities/cocoa/ghana", headers=UA, timeout=40); t = txt(r.text)
i = t.find("Price layers"); print("GHANA COCOA", t[i:i + 900])
for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.S):
    if "Dataset" in m: print("DATASET", m[:1200])
r = requests.get("https://www.mansamarkets.com/disclosures", headers=UA, timeout=40); t = txt(r.text); print("DISCLOSURES", t[:1500])
for u in ["https://www.tmx.co.tz/market_data/recent-trade-results", "https://www.tmx.co.tz/market_data/overall-data", "https://indianspices.com/dailyprice-auctiondetails.html"]:
    r = requests.get(u, headers=UA, timeout=40); t = txt(r.text)
    print("==", u, r.status_code, len(r.text), "tables", r.text.count("<table"), "| json", "__NEXT_DATA__" in r.text or "__next_f" in r.text)
    for k in ("Cashew", "Sesame", "Price", "Rs./Kg"):
        j = t.find(k)
        if j > 0: print("   ", k, "::", t[max(0, j - 200):j + 500]); break
