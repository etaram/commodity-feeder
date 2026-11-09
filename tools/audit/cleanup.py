import json, os, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
cr = service_account.Credentials.from_service_account_info(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=["https://www.googleapis.com/auth/spreadsheets"]); cr.refresh(Request())
H = {"Authorization": f"Bearer {cr.token}"}
LE = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y"; API = "https://sheets.googleapis.com/v4/spreadsheets"
m = requests.get(f"{API}/{LE}?fields=sheets.properties(title,sheetId)", headers=H, timeout=120).json()
ids = [s["properties"]["sheetId"] for s in m["sheets"] if s["properties"]["title"] == "zz audit probe"]
print("probe tabs:", ids)
for i in ids: print(requests.post(f"{API}/{LE}:batchUpdate", headers=H, json={"requests": [{"deleteSheet": {"sheetId": i}}]}, timeout=180).status_code)
# which tabs hold formulas over the big tabs: full-tab formula scan of the dashboard tabs
for t in ["Home", "Search", "Pipeline", "Deals", "Markets", "Israel Overview", "USA", "Commodities"]:
    r = requests.get(f"{API}/{LE}/values/'{t}'!A1:Z400", params={"valueRenderOption": "FORMULA"}, headers=H, timeout=120)
    fs = [c for row in r.json().get("values", []) for c in row if isinstance(c, str) and c.startswith("=")]
    print(f"\n== {t}: {len(fs)} formulas"); [print("   ", f[:150]) for f in fs[:6]]
