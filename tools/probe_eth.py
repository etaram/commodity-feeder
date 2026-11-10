import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
h = requests.get("https://eatta.co.ke/statistics", headers=UA, timeout=40).text
print("scripts", re.findall(r'<script[^>]+src="([^"]+)"', h))
print("fetch/api", sorted(set(re.findall(r'(?:fetch\(|url:\s*|src=|href=)["\']([^"\']*(?:api|json|xlsx|csv|report|result)[^"\']*)', h, re.I)))[:20])
for s in re.findall(r'<script[^>]*>(.*?)</script>', h, re.S):
    for m in re.findall(r'["\'](https?://[^"\']+|/[a-zA-Z0-9_\-/.]+\.(?:json|php|aspx|xlsx|csv)[^"\']*)["\']', s)[:20]: print("   js url", m)
for js in re.findall(r'<script[^>]+src="(/[^"]+\.js[^"]*)"', h)[:4]:
    r = requests.get("https://eatta.co.ke" + js, headers=UA, timeout=40)
    print("== JS", js, r.status_code, len(r.text), sorted(set(re.findall(r'["\'`](https?://[^"\'`\s]+|/[a-zA-Z0-9_\-/.]*(?:api|json|data|report|stat)[^"\'`\s]*)["\'`]', r.text)))[:20])
