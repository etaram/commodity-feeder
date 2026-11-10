import re, requests, json
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "en"}
h = requests.get("https://royalcoffee.com/offerings/?country=ethiopia", headers=UA, timeout=40).text
print("len", len(h), "tables", h.count("<table"), "json-ld", h.count("application/ld+json"), "wp-json", "wp-json" in h)
for m in list(re.finditer(r"[$]\s?\d+[.]\d\d", h))[:6]:
    print("HTML>>", re.sub(r"\s+", " ", h[max(0, m.start() - 700):m.start() + 120]))
    print("-----")
for m in list(re.finditer(r"(?i)ethiopia", h))[:400:60]:
    print("ETH>>", re.sub(r"\s+", " ", h[max(0, m.start() - 150):m.start() + 350]))
for u in ["https://royalcoffee.com/wp-json/wc/store/products?per_page=5&search=ethiopia", "https://royalcoffee.com/wp-json/wp/v2/types", "https://royalcoffee.com/robots.txt"]:
    try:
        r = requests.get(u, headers=UA, timeout=30); print("API", u[-60:], r.status_code, r.text[:600].replace("\n", " "))
    except Exception as e: print("API ERR", e)
