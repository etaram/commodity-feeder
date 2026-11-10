import re, requests, json
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
for js in ["/js/live-stats.js?v=20261104d", "/js/weekly-report.js?v=20261104d"]:
    r = requests.get("https://eatta.co.ke" + js, headers=UA, timeout=40)
    urls = sorted(set(re.findall(r'["\'`]((?:https?://|/)[^"\'`\s]{4,120})["\'`]', r.text)))
    print("== JS", js, r.status_code, len(r.text), urls[:20])
    i = r.text.find("fetch("); print("   ctx", r.text[max(0, i - 300):i + 500].replace("\n", " "))
