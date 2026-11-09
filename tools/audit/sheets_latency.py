"""Times the Deal Desk's live Google Sheets reads and lists the size of every tab (audit, read-only)."""
import json, os, time, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
cr = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
t = time.time(); cr.refresh(Request()); print(f"token {time.time()-t:.2f}s")
H = {"Authorization": f"Bearer {cr.token}"}
LE, SU = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y", "1crzrRr4qrgt1WpAwNmCNPL4TfIrZUuTyqRGonVvwhuA"
LIVE = {"bd": (LE, "'BD Agent'!A1:M600"), "accounts": (LE, "'Key Accounts'!A1:S400"), "intel": (LE, "'Intel'!A1:P2000"),
        "pursuits": (LE, "'Pursuits'!A1:V600"), "jobs": (LE, "'Panel Jobs'!A1:L800"), "contacts": (LE, "'Contacts'!A1:S1500"),
        "projects": (LE, "'Projects'!A1:V300"), "websup": (LE, "'Web Suppliers'!A1:J3000"), "ptasks": (LE, "'Project Tasks'!A1:L3000"),
        "approvals": (LE, "'Approvals'!A1:M2000"), "stats": (SU, "'Stats'!A1:B60"), "users": (LE, "'Users'!A1:Z300"), "tglinks": (LE, "'Telegram Links'!A1:F500")}
for sid in (LE, SU):
    t = time.time()
    m = requests.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}?fields=sheets.properties(title,gridProperties)", headers=H, timeout=60).json()
    tabs = [(s["properties"]["title"], s["properties"]["gridProperties"].get("rowCount", 0) * s["properties"]["gridProperties"].get("columnCount", 0)) for s in m.get("sheets", [])]
    print(f"\n{sid[:6]} meta {time.time()-t:.2f}s tabs={len(tabs)} cells={sum(c for _, c in tabs):,}")
    for n, c in sorted(tabs, key=lambda x: -x[1])[:25]: print(f"   {c:>12,}  {n}")
for rnd in range(3):
    print(f"\nround {rnd+1}")
    for k, (sid, rg) in LIVE.items():
        t = time.time()
        try:
            r = requests.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values:batchGet", params={"ranges": rg, "valueRenderOption": "FORMATTED_VALUE"}, headers=H, timeout=60)
            n = len((r.json().get("valueRanges") or [{}])[0].get("values", [])) if r.ok else r.status_code
        except Exception as e: n = repr(e)[:60]
        print(f"   {k:10} {time.time()-t:6.2f}s rows={n}")
