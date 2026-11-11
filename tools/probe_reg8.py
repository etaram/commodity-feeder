"""Gap commodities (sugar, pulses, tea, cotton, fertiliser): structure of candidate official member lists."""
import io, re, requests
from urllib import robotparser
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
def clean(h):
    b = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<header.*?</header>|<footer.*?</footer>", " ", h, flags=re.S)
    return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", b)))
def ok(url):
    m = re.match(r"(https?://[^/]+)", url); rp = robotparser.RobotFileParser(m.group(1) + "/robots.txt")
    try: rp.read(); return rp.can_fetch(UA["User-Agent"], url)
    except Exception as e: return f"? {type(e).__name__}"
PAGES = [
  ("apeda", "https://agriexchange.apeda.gov.in/AgriDirectory/Exporter/Exporters?page=122"),
  ("usapulses", "https://www.usapulses.org/suppliers/exporters?start=30"),
  ("bonsucro", "https://bonsucro.com/bonsucro-members"),
  ("psma", "https://psma.com.ph/members-and-industry-partners"),
  ("fert_au", "https://fertilizer.org.au/about-us/currentmembers"),
  ("lk_tea", "https://www.srilankabusiness.com/exporters-directory/tea-exporters-in-sri-lanka/page4.html"),
  ("icaindia_pdf", "https://www.icaindia.co.in/pdf/Annual-Ordinary-Members.pdf"),
  ("psac_merch", "https://icac.org/wp-content/uploads/2024/11/psac_merchants_membership_10_14_22.pdf"),
]
for name, url in PAGES:
    try:
        rb = ok(url)
        r = requests.get(url, headers=UA, timeout=(10, 40)); print(f"== {name} {r.status_code} robots={rb} len={len(r.content)} type={r.headers.get('content-type','')[:30]} url={r.url[:90]}")
        if url.endswith(".pdf") and r.ok:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                print("   pages", len(pdf.pages)); print("   text:", re.sub(r"\s+", " ", (pdf.pages[0].extract_text() or ""))[:1200])
            continue
        h = r.text; t = clean(h)
        trs = re.findall(r"<tr.*?</tr>", h, flags=re.S); print("   tr:", len(trs))
        for tr in trs[1:4]:
            print("     ", [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()[:35] for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)][:9])
        print("   links:", [l for l in re.findall(r'href="([^"]+)"', h) if re.search(r"page|start=|member|exporter|detail|profile", l, re.I)][:10])
        i = max(0, len(t) // 5)
        print("   text:", t[i:i+1500])
    except Exception as e:
        print(f"== {name} ERR {type(e).__name__}: {str(e)[:110]}")
