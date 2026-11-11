import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
h = requests.get("https://agriexchange.apeda.gov.in/AgriDirectory/Exporter/Exporters?page=1", headers=UA, timeout=(10, 40)).text
i = h.find("Click here to contact")
print("ROW HTML:", re.sub(r"\s+", " ", h[max(0, i - 1800):i + 400]))
print("LAST PAGES:", sorted({int(x) for x in re.findall(r"Exporters\?page=(\d+)", h)})[-5:])
m = re.search(r'href="([^"]*)"[^>]*>\s*Click here to contact', h) or re.search(r"Click here to contact.{0,200}", h, re.S)
print("CONTACT:", m.group(0)[:400] if m else None)
link = re.search(r'href="(/AgriDirectory/Exporter/[^"]+)"', h[max(0, i - 600):i + 50])
if link:
    d = requests.get("https://agriexchange.apeda.gov.in" + link.group(1), headers=UA, timeout=(10, 40))
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", d.text, flags=re.S)))
    j = t.find("Contact"); print("DETAIL", d.status_code, d.url[:120]); print(t[max(0, j - 200):j + 1500])
h2 = requests.get("https://www.srilankabusiness.com/exporters-directory/tea-exporters-in-sri-lanka/page4.html", headers=UA, timeout=(10, 40)).text
k = h2.find("company-name"); k = k if k > 0 else h2.find("exporter-name")
print("LK:", re.sub(r"\s+", " ", h2[k - 300:k + 1500]) if k > 0 else re.findall(r'class="([^"]*(?:company|exporter|list|item)[^"]*)"', h2)[:20])
