import requests
U = "https://datacatalogapi.worldbank.org/dexapps/fone/api/view"
for p in [{"viewId": "DS00005", "top": 3, "type": "json"},
          {"viewId": "DS00005", "top": 3, "type": "json", "filter": "fiscal_year=2026"},
          {"viewId": "DS00005", "top": 3, "type": "json", "filter": "fiscal_year='2026'"},
          {"viewId": "DS00005", "top": 3, "type": "json", "filter": "fiscal_year = 2026"},
          {"viewId": "DS00005", "top": 3, "type": "json", "filter": "borrower_country=Kenya"},
          {"viewId": "DS00005", "top": 3, "type": "json", "orderby": "contract_signing_date desc"}]:
    r = requests.get(U, params=p, timeout=60)
    t = r.text
    print(p.get("filter") or p.get("orderby") or "plain", r.status_code, t[:300].replace("\n", " "))
