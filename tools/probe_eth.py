import re, requests, json
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderPriceProbe/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
for u in ["https://ethiopianexportmarket.com/robots.txt", "https://ethiopianexportmarket.com/insight", "https://ecx.eem.et/", "https://ecx.eem.et/robots.txt", "https://ethiopianexportmarket.com/marketplace"]:
    try:
        r = requests.get(u, headers=UA, timeout=40); h = r.text
        print("=====", u, r.status_code, len(h))
        if "robots" in u: print(h[:700]); continue
        print("next_data", "__NEXT_DATA__" in h, "| nuxt", "__NUXT__" in h, "| tables", h.count("<table"), "| scripts", [s for s in re.findall(r'<script[^>]+src="([^"]+)"', h)][:8])
        apis = sorted(set(re.findall(r'https?://[a-zA-Z0-9.\-]*eem\.et[^"\'\s<>\\]*|/api/[a-zA-Z0-9_\-/]+|https?://[^"\'\s<>\\]*(?:supabase|firebase|graphql|strapi|/api/)[^"\'\s<>\\]*', h)))[:40]
        print("apis", apis)
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)))
        for k in ("Minimum", "Sidamo", "Closing", "Top Exporter", "Birr", "USc/lb"):
            m = re.search(k, t)
            if m: print("  CTX", k, "::", t[max(0, m.start() - 100):m.start() + 500])
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
        if m:
            d = json.loads(m.group(1)); print("  NEXT keys", list(d.get("props", {}).get("pageProps", {}).keys())[:30], "buildId", d.get("buildId"))
            print("  NEXT sample", json.dumps(d.get("props", {}).get("pageProps", {}))[:1500])
        for chunk in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', h, re.S)[:400]:
            if re.search(r"Sidamo|minimum|closing|exporter", chunk, re.I): print("  RSC", chunk[:700].replace("\\n", " ")); break
    except Exception as e:
        print("ERR", u, str(e)[:120])
