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

    def replace_tab(self, sid, title, rows, chunk=5000, clear_to=None, raw=False):
        """Writes rows (first row = header) to the tab, then clears what is left below - only in the data columns
        (clear_to = last data column letter) so formula columns to the right are kept."""
        ncols = max(len(r) for r in rows) if rows else 1
        self.ensure_tab(sid, title, len(rows) + 10, ncols)
        q = title.replace("'", "''")
        for i in range(0, len(rows), chunk):
            self._req("PUT", f"{API}/{sid}/values/'{q}'!A{i + 1}", params={"valueInputOption": "RAW" if raw else "USER_ENTERED"},
                      json={"values": rows[i:i + chunk]})
        self._req("POST", f"{API}/{sid}/values/'{q}'!A{len(rows) + 1}:{clear_to or 'ZZ'}:clear", json={})
        return len(rows)


def col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


def leads_tables():
    """(tab, rows) for the Leads Engine sheet, full size (no IMPORTDATA limit)."""
    from .common import LEADS
    out = []
    chunks = sorted((LEADS / "sheet").glob("tenders_[0-9][0-9].csv"))
    rows = []
    for i, f in enumerate(chunks):
        r = read_csv(f)
        rows += r if i == 0 else r[1:]
    out.append(("Tenders", [x for x in rows if any(x)]))
    for tab, name in [("Opportunity Pool", "opportunities"), ("Repeat Buyers", "buyers"), ("Awards", "awards"),
                      ("Competitors", "competitors"), ("Accounts", "accounts"), ("Importers", "importers"),
                      ("Sectors", "sectors"), ("Countries", "countries"), ("Sources", "status"),
                      ("Market Signals", "markets"), ("Suppliers", "suppliers"), ("Groups", "groups")]:
        full = LEADS / f"{name}_all.csv"
        out.append((tab, read_csv(full if full.exists() else LEADS / f"{name}.csv")))
    dg = LEADS / "digest.txt"
    if dg.exists():
        out.append(("Digest", [["daily digest"]] + [[line] for line in dg.read_text(encoding="utf-8").splitlines()]))
    return out


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return [row for row in csv.reader(f)]


def main():
    a = sys.argv[1:]
    sh = Sheets()
    if a[:1] == ["check"]:
        for sid in (LEADS_SHEET, UNIVERSE_SHEET):
            print("OK", sid, sh.meta(sid)["properties"]["title"])
    elif a[:1] == ["universe"]:
        from .common import PRIVATE
        rows = read_csv(PRIVATE / "universe.csv")[:150_001]  # sorted by quality; full file stays in the private cache
        for r in rows[1:]:
            for i in (rows[0].index("quality"), rows[0].index("wins"), rows[0].index("won_usd_est"), rows[0].index("buyers")):
                try:
                    r[i] = int(r[i])
                except ValueError:
                    pass
        print("wrote", sh.replace_tab(UNIVERSE_SHEET, "Suppliers", rows, raw=True), "rows to Supplier Universe")
        st = json.loads((PRIVATE / "universe_stats.json").read_text())
        sh.replace_tab(UNIVERSE_SHEET, "Stats", [["metric", "value"]] + [[k, v] for k, v in st.items()] +
                       [["updated_utc", time.strftime("%Y-%m-%d %H:%M")]], raw=True)
    elif a[:1] == ["leads"]:
        for tab, rows in leads_tables():
            if len(rows) < 2:
                print("skip", tab, "(no data)"); continue
            width = max(len(r) for r in rows)
            n = sh.replace_tab(LEADS_SHEET, tab, rows, clear_to=col_letter(width))
            print("wrote", n, "rows x", width, "cols to", tab)
    elif a[:1] == ["tab"]:
        n = sh.replace_tab(a[1], a[2], read_csv(a[3]))
        print("wrote", n, "rows to", a[2])


if __name__ == "__main__":
    main()
