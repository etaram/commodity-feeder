"""Push data straight into Google Sheets with a service account (no IMPORTDATA size limit, private data never has
to sit in a public file). Activated when the GOOGLE_SERVICE_ACCOUNT_JSON secret is present.

  python -m leads.push check                          verify access to both sheets
  python -m leads.push tab <sheet_id> <tab> <csv>     replace a tab with a CSV
"""
import csv
import json
import os
import sys
import time

import requests

API = "https://sheets.googleapis.com/v4/spreadsheets"
LEADS_SHEET = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y"
UNIVERSE_SHEET = "1crzrRr4qrgt1WpAwNmCNPL4TfIrZUuTyqRGonVvwhuA"


def _token():
    info = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not info:
        raise SystemExit("GOOGLE_SERVICE_ACCOUNT_JSON is not set")
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_info(
        json.loads(info), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(Request())
    return creds.token


class Sheets:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {_token()}"

    def _req(self, method, url, **kw):
        for attempt in range(5):
            r = self.s.request(method, url, timeout=120, **kw)
            if r.status_code in (429, 500, 503):
                time.sleep(5 * (attempt + 1)); continue
            if r.status_code >= 400:
                raise RuntimeError(f"{r.status_code} {r.text[:300]}")
            return r.json() if r.text else {}
        raise RuntimeError("Sheets API retries exhausted")

    def meta(self, sid):
        return self._req("GET", f"{API}/{sid}", params={"fields": "properties.title,sheets.properties"})

    def ensure_tab(self, sid, title, rows, cols):
        m = self.meta(sid)
        tab = next((x["properties"] for x in m["sheets"] if x["properties"]["title"] == title), None)
        reqs = []
        if not tab:
            reqs.append({"addSheet": {"properties": {"title": title, "gridProperties": {"rowCount": rows, "columnCount": cols}}}})
        else:
            g = tab["gridProperties"]
            if g["rowCount"] < rows or g["columnCount"] < cols:
                reqs.append({"updateSheetProperties": {"properties": {"sheetId": tab["sheetId"], "gridProperties": {
                    "rowCount": max(rows, g["rowCount"]), "columnCount": max(cols, g["columnCount"])}},
                    "fields": "gridProperties.rowCount,gridProperties.columnCount"}})
        if reqs:
            self._req("POST", f"{API}/{sid}:batchUpdate", json={"requests": reqs})

    def replace_tab(self, sid, title, rows, chunk=5000):
        """Writes rows (first row = header) to the tab, then clears anything below."""
        ncols = max(len(r) for r in rows) if rows else 1
        self.ensure_tab(sid, title, len(rows) + 10, ncols)
        q = title.replace("'", "''")
        for i in range(0, len(rows), chunk):
            self._req("PUT", f"{API}/{sid}/values/'{q}'!A{i + 1}", params={"valueInputOption": "USER_ENTERED"},
                      json={"values": rows[i:i + chunk]})
        self._req("POST", f"{API}/{sid}/values/'{q}'!A{len(rows) + 1}:ZZ:clear", json={})
        return len(rows)


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return [row for row in csv.reader(f)]


def main():
    a = sys.argv[1:]
    sh = Sheets()
    if a[:1] == ["check"]:
        for sid in (LEADS_SHEET, UNIVERSE_SHEET):
            print("OK", sid, sh.meta(sid)["properties"]["title"])
    elif a[:1] == ["tab"]:
        n = sh.replace_tab(a[1], a[2], read_csv(a[3]))
        print("wrote", n, "rows to", a[2])


if __name__ == "__main__":
    main()
