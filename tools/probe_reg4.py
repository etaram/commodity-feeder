import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
def txt(h):
    b = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", b))
h = requests.get("https://vietfood.org.vn/hoi-vien/danh-sach-cac-thuong-nhan-du-dieu-kien-kinh-doanh-xuat-khau-gao/", headers=UA, timeout=30).text
m = re.search(r'<(main|article|div[^>]*class="[^"]*(entry-content|content-area|site-main|post)[^"]*")', h)
print("VFA main tag at", m.start() if m else None)
t = txt(h[m.start():] if m else h); i = t.find("đủ điều kiện"); print("VFA:", t[i:i+1800])
h = requests.get("https://vietfood.org.vn/hoi-vien/danh-sach-hoi-vien/", headers=UA, timeout=30).text
m = re.search(r'<(main|article)', h); t = txt(h[m.start():] if m else h); print("VFA members:", t[:1500])
h = requests.get("https://www.reap.com.pk/memberDetails/4", headers=UA, timeout=30).text
t = txt(h); i = t.find("Membership"); print("REAP detail:", t[i:i+1200])
for u in ("https://iranpistachio.org/en/members/view/form/catid/4?catid=4&page=2", "https://iranpistachio.org/en/members/view/form/catid/4/page/2?catid=4", "https://iranpistachio.org/en/members/view/form/catid/4?catid=4&p=2"):
    h = requests.get(u, headers=UA, timeout=30).text
    rows = re.findall(r"<tr.*?</tr>", h, flags=re.S); first = re.sub(r"<[^>]+>", " ", rows[1])[:80] if len(rows) > 1 else ""
    print("IPA", u[-30:], len(rows), re.sub(r"\s+", " ", first)); 
    print("   pager:", re.findall(r'href="([^"]*(page|p=)[^"]*)"', h)[:6])
