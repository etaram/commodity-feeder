"""One-time repair: state tabs that were created by their first append have no header row, while the app reads them
from row 2, so the first record of each was never read (the deal agent's first run on 9 Nov stayed "running" for this
reason). For each listed tab that exists and whose A1 is not the marker, insert one row at the top and write the
marker "#". Idempotent. Dry run unless --apply. Prints tab names and actions only, never cell contents.

Environment: GOOGLE_SERVICE_ACCOUNT_JSON, STATE_SHEET_ID."""
import json
import os
import sys

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

TABS = ["Agent Runs", "Agent Approvals", "App Log", "AI Usage", "Telegram Chat", "Assertions", "Coverage Cache", "Locks", "Tender Projects", "Tender Watches"]
API = "https://sheets.googleapis.com/v4/spreadsheets"


def main(apply):
    sid = os.environ["STATE_SHEET_ID"]
    cred = service_account.Credentials.from_service_account_info(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    s = AuthorizedSession(cred)
    meta = s.get(f"{API}/{sid}", params={"fields": "sheets.properties(title,sheetId)"}, timeout=60).json()
    ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in meta.get("sheets", [])}
    for tab in TABS:
        if tab not in ids:
            print(f"{tab}: absent (the app will create it with a marker row)"); continue
        v = s.get(f"{API}/{sid}/values/'{tab}'!A1:A2", timeout=60).json().get("values", [])
        a1 = (v[0][0] if v and v[0] else "")
        if a1 == "#":
            print(f"{tab}: already has the marker row"); continue
        action = "write marker in the empty first row" if not v else "insert a marker row above the first record"
        if not apply:
            print(f"{tab}: WOULD {action}"); continue
        if v:
            r = s.post(f"{API}/{sid}:batchUpdate", json={"requests": [{"insertDimension": {"range": {"sheetId": ids[tab], "dimension": "ROWS", "startIndex": 0, "endIndex": 1}, "inheritFromBefore": False}}]}, timeout=60)
            r.raise_for_status()
        r = s.put(f"{API}/{sid}/values/'{tab}'!A1", params={"valueInputOption": "RAW"}, json={"values": [["#"]]}, timeout=60)
        r.raise_for_status()
        print(f"{tab}: done ({action})")


if __name__ == "__main__":
    main("--apply" in sys.argv)
