import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
r = requests.get("https://oncc.cm/resources/list-of-active-cocoa---coffee-exporters-2025", headers=UA, timeout=40); h = r.text; t = txt(h)
print("== ONCC list", r.status_code, len(h), "tables", h.count("<table"), "pdf", sorted(set(re.findall(r'href="([^"]*\.pdf[^"]*)"', h)))[:5])
i = t.find("Exporters"); print("   ", t[i:i + 2500])
r = requests.get("https://oncc.cm/robots.txt", headers=UA, timeout=20); print("== ONCC robots", r.status_code, r.text[:200])
# NEPC: pagination of the directory
r = requests.get("https://nepc.gov.ng/importer/find-your-supplier/", headers=UA, timeout=40); h = r.text; t = txt(h)
print("== NEPC", "READ MORE" , t.count("READ MORE"), "| pager", sorted(set(re.findall(r'href="([^"]*wpv_paged[^"]*|[^"]*find-your-supplier/page/\d+[^"]*)"', h)))[:6], "| data", re.findall(r'data-pagination="([^"]{0,200})', h)[:1])
print("   links", sorted(set(re.findall(r'href="(https://nepc\.gov\.ng/importer/(?:supplier|exporter|company)[^"]*)"', h)))[:8])
for m in re.finditer(r"\| ([A-Z][^|]{3,60}(?:Ltd|Limited|Group|Cocoa|Nigeria|PLC|Company|Industries)[^|]{0,30}) \| (?:Certifications: \| ([^|]+) \| )?Size: \| ([^|]+) \| ([^|]{40,})\| READ MORE", t):
    print("   CARD", m.group(1).strip(), "|", (m.group(2) or "").strip(), "|", m.group(3).strip(), "|", m.group(4).strip()[:120])
