import re, requests, io, json, pdfplumber
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
# ONCC Cameroon exporters page
r = requests.get("https://oncc.cm/exporters", headers=UA, timeout=40); h = r.text; t = txt(h)
print("== ONCC exporters", r.status_code, len(h), "tables", h.count("<table"), "| links", sorted(set(re.findall(r'href="([^"]*(?:export|pdf|xls)[^"]*)"', h, re.I)))[:10])
i = t.find("Export"); print("   ", t[i:i + 1500])
# NEPC: the supplier list is rendered by WP Views; the page HTML may already hold the cards
r = requests.get("https://nepc.gov.ng/importer/find-your-supplier/", headers=UA, timeout=40); h = r.text; t = txt(h)
cards = re.findall(r'wpv-loop|supplier-card|class="[^"]*exporter[^"]*"', h); print("== NEPC markers", len(cards), set(cards))
i = t.find("Check out all av"); print("   ", t[i:i + 1800])
print("   NEPC ajax", sorted(set(re.findall(r'"(wpv_[a-z_]+)"', h)))[:10], re.findall(r'data-viewnumber="(\d+)"', h)[:5])
# ICO certifying agents pdf: countries and agencies (official per-country registry of who certifies coffee exports)
r = requests.get("https://ico.org/documents/cy2025-26/ed-2500-r1e-certifying-agents-ports.pdf", headers=UA, timeout=60)
with pdfplumber.open(io.BytesIO(r.content)) as d:
    print("== ICO pages", len(d.pages)); print("   ", re.sub(r"\s+", " ", d.pages[1].extract_text() or "")[:1200])
