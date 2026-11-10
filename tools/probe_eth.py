import re, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "en"}
for u in ["https://www.rainforest-alliance.org/business/certification/certificate-search-and-public-summaries/", "https://www.flocert.net/about-flocert/customer-search/"]:
    h = requests.get(u, headers=UA, timeout=40).text
    print("=====", u, len(h), "tables", h.count("<table"), "tr", h.count("<tr"), "iframes", re.findall(r'<iframe[^>]+src="([^"]+)"', h)[:5])
    print("scripts", [s for s in re.findall(r'<script[^>]+src="([^"]+)"', h) if not re.search(r"jquery|gtm|google|cookie|wp-includes", s)][:12])
    print("endpoints", sorted(set(re.findall(r'https?://[^"\'\s<>]+(?:api|json|ajax|search|csv|xlsx|airtable|powerbi|tableau|datawrapper|salesforce)[^"\'\s<>]*', h)))[:15])
    print("forms", re.findall(r'<form[^>]*action="([^"]*)"', h)[:5], "selects", re.findall(r'<select[^>]*name="([^"]*)"', h)[:10])
    for m in list(re.finditer(r"Ethiopia|Coffee", h))[:3]:
        print("  CTX", re.sub(r"\s+", " ", h[max(0, m.start() - 300):m.start() + 400]))
