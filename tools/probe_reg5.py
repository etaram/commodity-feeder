import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
def clean(h):
    b = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", b)))
PAGES = [
    ("aeki", "https://www.aeki-aice.org/en/members/", "Member List"),
    ("fpef", "https://www.fpef.co.za/exporter-members", "EXPORTER"),
    ("fpef2", "https://www.fpef.co.za/", "EXPORTER MEMBERS"),
    ("cecafe", "https://www.cecafe.com.br/associados/", "Associados"),
    ("capeco", "https://capeco.org.py/socios/", "SOCIOS"),
    ("uzex", "https://uzex.uz/en/trades", "Weekly"),
    ("amecafe", "https://amecafe.org.mx/precios-del-cafe-en-el-mercado/", "Precio"),
    ("cga", "https://www.cga.co.za/", "Member"),
]
for name, url, key in PAGES:
    try:
        r = requests.get(url, headers=UA, timeout=(8, 20)); h = r.text
        t = clean(h); i = max(t.find(key), 0)
        print(f"== {name} {r.status_code} len={len(h)} url={r.url}")
        trs = re.findall(r"<tr.*?</tr>", h, flags=re.S); print("   tr:", len(trs))
        for tr in trs[:3]:
            print("     ", [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()[:40] for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)][:8])
        print("   links:", [l for l in re.findall(r'href="([^"]+)"', h) if re.search(r"member|associad|socio|anggota|exporter|page/", l, re.I)][:8])
        print("   text:", t[i:i+1500])
    except Exception as e:
        print(f"== {name} ERR {type(e).__name__}: {str(e)[:100]}")
