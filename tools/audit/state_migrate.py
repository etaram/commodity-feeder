"""Moves the app's write-heavy tabs from the engine sheet to the state sheet (copy; the engine copies stay as a backup).
Usage: STATE_SHEET_ID=<id> python tools/audit/state_migrate.py   (without the id it only prints the service account)."""
import json, os, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
print("service account:", info["client_email"])
ST = os.environ.get("STATE_SHEET_ID", "").strip()
if not ST: raise SystemExit(0)
cr = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"]); cr.refresh(Request())
H = {"Authorization": f"Bearer {cr.token}"}
LE = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y"; API = "https://sheets.googleapis.com/v4/spreadsheets"
TABS = ["Activity", "App Log", "AI Usage", "Telegram Chat", "Telegram", "Agent Runs", "Agent Approvals", "Locks", "Tender Projects", "Tender Watches", "Briefs"]
have = {s["properties"]["title"] for s in requests.get(f"{API}/{ST}?fields=sheets.properties(title)", headers=H, timeout=120).json()["sheets"]}
src = {s["properties"]["title"] for s in requests.get(f"{API}/{LE}?fields=sheets.properties(title)", headers=H, timeout=180).json()["sheets"]}
for t in TABS:
    if t not in src: print(f"{t}: not in the engine sheet, skipped"); continue
    r = requests.get(f"{API}/{LE}/values/'{t}'!A1:AN60000", params={"valueRenderOption": "FORMATTED_VALUE"}, headers=H, timeout=300)
    v = r.json().get("values", [])
    if t not in have:
        requests.post(f"{API}/{ST}:batchUpdate", headers=H, json={"requests": [{"addSheet": {"properties": {"title": t, "gridProperties": {"rowCount": max(1000, len(v) + 500), "columnCount": 40}}}}]}, timeout=120).raise_for_status()
    else:
        requests.post(f"{API}/{ST}/values/'{t}'!A1:AN60000:clear", headers=H, json={}, timeout=120)
    for i in range(0, len(v), 5000):
        requests.put(f"{API}/{ST}/values/'{t}'!A{i+1}", params={"valueInputOption": "RAW"}, headers=H, json={"values": v[i:i+5000]}, timeout=300).raise_for_status()
    back = len(requests.get(f"{API}/{ST}/values/'{t}'!A1:A60000", headers=H, timeout=120).json().get("values", []))
    print(f"{t}: {len(v)} rows copied, {back} rows in the state sheet")
