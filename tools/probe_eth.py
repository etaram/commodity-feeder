import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderPriceProbe/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def text(u):
    h = requests.get(u, headers=UA, timeout=40).text
    return h, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)))
h, t = text("https://ethiopianexportmarket.com/insight")
t = re.sub(r"(\| )+", "| ", t)
i = t.find("Top coffee exporters"); print("EXPORTERS", t[i:i + 2200])
i = t.find("Top coffee buyers"); print("BUYERS", t[i:i + 700])
i = t.find("Roasted coffee prices"); print("ROAST", t[i - 500:i + 300])
print("exporter rows guess", len(re.findall(r"\$ ?[\d.,]+ ?M", t)))
h, t = text("https://ethiopianexportmarket.com/marketplace")
t = re.sub(r"(\| )+", "| ", t)
i = t.find("per ton"); print("MARKET", t[max(0, i - 600):i + 1800])
print("cards", t.count("per ton"), "| pages", sorted(set(re.findall(r'href="(/marketplace[^"]*)"', h)))[:25])
s = requests.get("https://ethiopianexportmarket.com/sitemap.xml", headers=UA, timeout=40).text
print("SITEMAP", len(s), re.findall(r"<loc>([^<]+)</loc>", s)[:40])
