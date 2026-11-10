import re, requests, io, pdfplumber
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
r = requests.get("https://oncc.cm/content/library/documents/resource-list-of-active-c-1761643595.pdf", headers=UA, timeout=60); print("pdf", r.status_code, len(r.content))
with pdfplumber.open(io.BytesIO(r.content)) as d:
    print("pages", len(d.pages))
    for i in (0, 1, len(d.pages) - 1):
        pg = d.pages[i]; print(f"--- p{i+1} text:", re.sub(r"\s+", " ", pg.extract_text() or "")[:1500])
        tb = pg.extract_tables(); print(f"--- p{i+1} tables:", len(tb), [t[:4] for t in tb][:1])
