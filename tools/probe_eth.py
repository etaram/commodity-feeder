import re, requests, io
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
def txt(h): return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
# 1. ICO certifying agents (every exporting member's certifying body + ports) - official
r = requests.get("https://ico.org/documents/cy2025-26/ed-2500-r1e-certifying-agents-ports.pdf", headers=UA, timeout=60); print("ICO pdf", r.status_code, len(r.content))
# 2. NEPC Nigeria exporters directory
for u in ["https://nepc.gov.ng/importer/find-your-supplier/", "https://nepc.gov.ng/robots.txt"]:
    r = requests.get(u, headers=UA, timeout=40); t = txt(r.text)
    print("== NEPC", u, r.status_code, len(r.text), "forms", re.findall(r'<form[^>]*action="([^"]*)"', r.text)[:3], "selects", re.findall(r'<select[^>]*name="([^"]*)"', r.text)[:6], "| api", sorted(set(re.findall(r'(?:admin-ajax|wp-json|/api/)[^"\' ]*', r.text)))[:6])
    i = t.find("Supplier"); print("   ", t[i:i + 600])
# 3. Vietnam licensed rice exporters: MOIT publishes a list; the news article names the count; find the source document
for u in ["https://moit.gov.vn/", "https://www.vietnamplus.vn/", "https://en.vietnamplus.vn/total-of-205-traders-allowed-to-export-rice-post195319.vnp"]:
    try:
        r = requests.get(u, headers=UA, timeout=40); t = txt(r.text); i = t.find("rice"); print("== VN", u[:60], r.status_code, len(r.text), t[max(0, i - 100):i + 500] if i > 0 else "")
    except Exception as e: print("== VN", u[:60], "ERR", str(e)[:80])
# 4. Kenya AFA licensed coffee dealers (152): find the pdf
for u in ["https://afa.go.ke/", "https://www.agricultureauthority.go.ke/", "https://coffee.afa.go.ke/"]:
    try:
        r = requests.get(u, headers=UA, timeout=40); print("== AFA", u, r.status_code, len(r.text), sorted(set(re.findall(r'href="([^"]*(?:licen|dealer|export|marketing|\.pdf)[^"]*)"', r.text, re.I)))[:10])
    except Exception as e: print("== AFA", u, "ERR", str(e)[:80])
# 5. Cameroon ONCC documents library
r = requests.get("https://oncc.cm/content/library/documents/NCCB-bilan-de-la-campagne-cacaoyere-2022-2023-1694445969.pdf", headers=UA, timeout=60); print("ONCC pdf", r.status_code, len(r.content))
try:
    r = requests.get("https://oncc.cm/", headers=UA, timeout=40); print("== ONCC", r.status_code, sorted(set(re.findall(r'href="([^"]*(?:export|liste|agr|\.pdf)[^"]*)"', r.text, re.I)))[:12])
except Exception as e: print("ONCC ERR", str(e)[:80])
