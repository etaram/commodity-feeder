import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
# BCR Rosario: full table and date header
r = requests.get("https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-locales-0", headers=UA, timeout=40); t = txt(r.text)
i = t.find("Soja"); print("BCR", t[max(0, i - 900):i + 1400])
# EATTA statistics page
for u in ["https://eatta.co.ke/statistics", "https://eatta.co.ke/statistics/", "https://eatta.co.ke/"]:
    r = requests.get(u, headers=UA, timeout=40)
    links = sorted(set(re.findall(r'href="([^"]*(?:statistic|sale|result|report|price)[^"]*)"', r.text, re.I)))[:12]
    print("== EATTA", u, r.status_code, len(r.text), links)
    if r.status_code == 200 and "statistic" in u:
        t = txt(r.text); i = t.find("Sale"); print("   ", t[max(0, i - 300):i + 1200])
# robots-restricted hosts that still matter: say so and skip (CEPEA, Bolsa de Cereales, IHCAFE disallow everything)
# VPSA pepper daily market page
r = requests.get("https://peppervietnam.com/", headers=UA, timeout=40); h = r.text
links = sorted(set(re.findall(r'href="(https://peppervietnam\.com/thi-truong-ho-tieu-ngay[^"]*)"', h)))[:3]
print("== VPSA links", links)
if links:
    r = requests.get(links[-1], headers=UA, timeout=40); t = txt(r.text); i = t.find("Đắk"); print("   VPSA", t[max(0, i - 600):i + 900])
# Tea Board India auction prices page
for u in ["https://www.teaboard.gov.in/TEABOARDCSM/NQ==", "https://www.teaboard.gov.in/WEEKLYPRICES/2026"]:
    r = requests.get(u, headers=UA, timeout=40); t = txt(r.text); i = t.find("Auction"); print("== TEABOARD", u, r.status_code, t[max(0, i - 200):i + 700])
