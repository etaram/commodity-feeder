import io, re, requests, pdfplumber
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
def pdf(u, pages=(0, 1, 2), n=1400):
    r = requests.get(u, headers=UA, timeout=90); print("==", u[-70:], r.status_code, len(r.content))
    if not r.ok: return
    with pdfplumber.open(io.BytesIO(r.content)) as d:
        print("   pages", len(d.pages))
        for i in pages:
            if i < len(d.pages):
                print(f"   --- p{i + 1}:", re.sub(r"\s+", " ", d.pages[i].extract_text() or "")[:n])
        for i, pg in enumerate(d.pages):
            tx = pg.extract_text() or ""
            if re.search(r"exporter", tx, re.I) and re.search(r"60.?kg|bags|share|%", tx, re.I):
                print(f"   EXPORTERS p{i + 1}:", re.sub(r"\s+", " ", tx)[:1800]); break
pdf("https://ugandacoffee.go.ug/Coffee_and_Cocoa_Directory.pdf", pages=(0, 3, 8, 15))
pdf("https://ugandacoffee.go.ug/sites/default/files/2026-10/12%20September%202026%20Report%20dpptx%20%281%29.pptx_Finalptx.pdf", pages=(0,))
for u in ["https://apps.fas.usda.gov/newgainapi/api/Report/GetReportsList?countryName=Thailand&reportTitle=Rice%20Price", "https://fas.usda.gov/data/search?keyword=rice%20price%20weekly%20thailand", "https://gain.fas.usda.gov/api/reports?country=Thailand&title=Rice%20Price%20-%20Weekly"]:
    try:
        r = requests.get(u, headers=UA, timeout=40); print("== GAIN", u[:80], r.status_code, len(r.text), re.findall(r'href="([^"]*[Rr]ice[^"]*[Ww]eekly[^"]*)"', r.text)[:4], r.text[:200].replace("\n", " "))
    except Exception as e: print("== GAIN ERR", str(e)[:100])
