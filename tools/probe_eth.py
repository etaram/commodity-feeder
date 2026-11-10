import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
h = requests.get("https://commodity-board.com/category/oil-seeds/sesame", headers=UA, timeout=40).text
print("CATS", sorted(set(re.findall(r'href="(/category/[^"#?]+)"', h)))[:80])
i = h.find("· FOB"); print("RAW", re.sub(r"\s+", " ", h[i - 1500:i + 500]))
t = re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
rows = re.findall(r"\| ([^|]{3,60}) \| ([^|]{0,80}) \| ([^|]{1,8}) \| ([^|·]{2,40}) · (FOB|FCA|CIF|CFR|EXW|DAP|DDP|FAS|CPT) \| ([€$])([\d.,]+) \| ([+\-−]?[\d.,]+) ?%", t)
print("ROWS", len(rows)); [print("  ", r) for r in rows[:12]]
i = t.find("· FOB"); print("TXT", t[max(0, i - 900):i + 300])
print("DATE", re.findall(r"(?:Updated|as of|Last update)[^|]{0,60}", t)[:5], re.findall(r'datetime="([^"]+)"', h)[:5])
for u in ["https://ugandacoffee.go.ug/index.php/resource-center/reports/monthly-reports", "https://www.algrano.com/sitemap.xml", "https://afca.coffee/members/"]:
    r = requests.get(u, headers=UA, timeout=40); x = r.text
    print("==", u, r.status_code, len(x), sorted(set(re.findall(r'(?:href="|<loc>)([^"<]*(?:\.pdf|sitemap[^"<]*\.xml|seller-profiles/\d[^"<?]*))', x)))[:14])
    if "afca" in u:
        tt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", x)); j = tt.find("Ethiopia"); print("  AFCA", len(re.findall(r"member", tt, re.I)), tt[tt.find("Corporate"):tt.find("Corporate") + 600])
