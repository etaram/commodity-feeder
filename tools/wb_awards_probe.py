import requests
U = "https://datacatalogapi.worldbank.org/dexapps/fone/api/view"
for p in [{"viewId": "DS01154", "top": 2, "type": "json"},
          {"viewId": "DS01702", "top": 2, "type": "json"},
          {"datasetId": "DS00005", "resourceId": "RS00005", "top": 2, "type": "json"},
          {"viewId": "DS01154", "top": 2, "type": "json", "filter": "fiscal_year=2026"},
          {"viewId": "DS01154", "top": 2, "type": "json", "filter": "borrower_country=Kenya|Ethiopia"}]:
    r = requests.get(U, params=p, timeout=60)
    print(p, r.status_code, r.text[:400].replace("\n", " "))
r = requests.get("https://datacatalogapi.worldbank.org/dexapps/fone/api/metadata", params={"assetId": "DS00005"}, timeout=60)
print("meta DS00005", r.status_code, r.text[:600].replace("\n", " "))
