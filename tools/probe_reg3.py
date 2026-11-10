"""Structure of the registry/price pages found: VFA Vietnam rice, REAP Pakistan, Iran Pistachio Association, GDT."""
import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
PAGES = [
    ("vfa_qualified", "https://vietfood.org.vn/hoi-vien/danh-sach-cac-thuong-nhan-du-dieu-kien-kinh-doanh-xuat-khau-gao/"),
    ("vfa_china", "https://vietfood.org.vn/hoi-vien/danh-sach-cac-thuong-nhan-xuat-khau-gao-sang-thi-truong-trung-quoc/"),
    ("vfa_members", "https://vietfood.org.vn/hoi-vien/danh-sach-hoi-vien/"),
    ("vfa_dom", "https://vietfood.org.vn/thi-truong/gia-noi-dia/"),
    ("vfa_exp", "https://vietfood.org.vn/thi-truong/gia-xuat-khau/"),
    ("reap_profile", "https://www.reap.com.pk/memberProfile"),
    ("ipa_exporters", "https://iranpistachio.org/en/members/view/form/catid/4?catid=4"),
    ("ipa_growers", "https://iranpistachio.org/en/members/view/form/catid/1?catid=1"),
    ("gdt_wmp", "https://www.globaldairytrade.info/en/product-results/whole-milk-powder/"),
]
for name, url in PAGES:
    try:
        r = requests.get(url, headers=UA, timeout=(10, 25)); h = r.text
        print(f"== {name} {r.status_code} len={len(h)} url={r.url}")
        body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
        rows = re.findall(r"<tr.*?</tr>", body, flags=re.S)
        print("   tr rows:", len(rows))
        for tr in rows[:4]:
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
            print("     ", cells[:10])
        links = [l for l in re.findall(r'href="([^"]+)"', h) if re.search(r"page/\d|\.pdf|\.xls|member|catid", l)][:10]
        print("   links:", links)
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
        i = max(txt.find("STT"), txt.find("No."), txt.find("Company"), 0)
        print("   text:", txt[i:i+900])
    except Exception as e:
        print(f"== {name} ERR {type(e).__name__}: {str(e)[:100]}")
