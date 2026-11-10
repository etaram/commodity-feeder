import requests, json
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept": "application/json"}
for u in ["https://eatta.co.ke/api/live-stats.php", "https://eatta.co.ke/api/sales-report.php?year=2026"]:
    r = requests.get(u, headers=UA, timeout=40); print("==", u, r.status_code, r.text[:1800])
