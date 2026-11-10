"""Look at member/exporter directory pages found in batch 3b, to write registry adapters."""
import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
PAGES = [
    ("reap_members", "https://www.reap.com.pk/members-profiles"),
    ("reap_members2", "https://www.reap.com.pk/members"),
    ("reap_home", "https://www.reap.com.pk/"),
    ("vfa_members", "https://vietfood.org.vn/hoi-vien/"),
    ("vfa_members2", "https://vietfood.org.vn/danh-sach-hoi-vien/"),
    ("vfa_home", "https://vietfood.org.vn/"),
    ("vpsa_members", "https://vpsaspice.org/hoi-vien/"),
    ("tzcashew_exp", "https://www.cashew.go.tz/"),
    ("iran_pist_en", "https://iranpistachio.org/en/"),
    ("gdt_results", "https://www.globaldairytrade.info/en/product-results/"),
    ("kik_prices", "https://www.kik.com.pg/industry/prices"),
    ("naeb_home", "https://www.naeb.gov.rw/"),
]
for name, url in PAGES:
    try:
        r = requests.get(url, headers=UA, timeout=(10, 25))
        h = r.text
        links = re.findall(r'href="([^"]+)"', h)
        hits = [l for l in links if re.search(r"member|hoi-vien|exporter|price|gia|directory|result", l, re.I)][:25]
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
        txt = re.sub(r"<[^>]+>", " ", txt); txt = re.sub(r"\s+", " ", txt)
        print(f"== {name} {r.status_code} len={len(h)} url={r.url}")
        print("   links:", hits)
        print("   text:", txt[:700])
        if name == "naeb_home":
            i = txt.find("Agri-exports data"); print("   NAEB:", txt[i:i+600])
    except Exception as e:
        print(f"== {name} ERR {type(e).__name__}: {str(e)[:100]}")
