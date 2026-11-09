"""Audit (read-only except one scratch tab): formulas per tab in the engine sheet, and read latency right after an append."""
import json, os, time, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
cr = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"]); cr.refresh(Request())
H = {"Authorization": f"Bearer {cr.token}"}
LE = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y"
API = "https://sheets.googleapis.com/v4/spreadsheets"
meta = requests.get(f"{API}/{LE}?fields=sheets.properties(title,gridProperties,hidden)", headers=H, timeout=60).json()
tabs = [s["properties"]["title"] for s in meta["sheets"]]
tot = 0
for t in tabs:
    r = requests.get(f"{API}/{LE}/values/{requests.utils.quote(repr(t) if False else chr(39)+t+chr(39))}!A1:AZ40", params={"valueRenderOption": "FORMULA"}, headers=H, timeout=60)
    v = r.json().get("values", []) if r.ok else []
    f = sum(1 for row in v for c in row if isinstance(c, str) and c.startswith("="))
    vol = sum(1 for row in v for c in row if isinstance(c, str) and any(k in c.upper() for k in ("IMPORTRANGE", "QUERY(", "NOW()", "TODAY()", "INDIRECT", "ARRAYFORMULA", "FILTER(", "VLOOKUP", "COUNTIF")))
    if f: print(f"formulas {f:4} volatile/heavy {vol:3}  {t}"); tot += f
print("tabs", len(tabs), "formula cells in first 40 rows:", tot)
def rd():
    t = time.time(); requests.get(f"{API}/{LE}/values:batchGet", params={"ranges": "'Users'!A1:B3"}, headers=H, timeout=60); return time.time() - t
print("baseline reads", [round(rd(), 2) for _ in range(3)])
# scratch tab, created once and removed at the end
requests.post(f"{API}/{LE}:batchUpdate", headers=H, json={"requests": [{"addSheet": {"properties": {"title": "zz audit probe", "hidden": True}}}]}, timeout=60)
for i in range(4):
    t = time.time()
    requests.post(f"{API}/{LE}/values/{requests.utils.quote(chr(39)+'zz audit probe'+chr(39))}!A1:append", params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}, headers=H, json={"values": [[time.time(), "probe"]]}, timeout=60)
    a = time.time() - t
    print(f"append {a:.2f}s, read right after {rd():.2f}s, again {rd():.2f}s")
sid = [s["properties"]["sheetId"] for s in requests.get(f"{API}/{LE}?fields=sheets.properties(title,sheetId)", headers=H, timeout=60).json()["sheets"] if s["properties"]["title"] == "zz audit probe"]
if sid: requests.post(f"{API}/{LE}:batchUpdate", headers=H, json={"requests": [{"deleteSheet": {"sheetId": sid[0]}}]}, timeout=60); print("scratch tab removed")
