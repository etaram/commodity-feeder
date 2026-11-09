"""Print the page text around a word and every link to a data file (xlsx, xls, csv, pdf) found on the pages of a URL list."""
import re, sys, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderPriceProbe/1.0)"}
for u in [l.strip() for l in open(sys.argv[1]) if l.strip()]:
    h = requests.get(u, headers=UA, timeout=40).text
    print("=====", u)
    print("files:", sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|pdf)[^"]*)"', h, re.I)))[:12])
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)))
    for m in list(re.finditer(sys.argv[2], t))[:3]:
        print("...", t[max(0, m.start() - 100):m.start() + 400])
