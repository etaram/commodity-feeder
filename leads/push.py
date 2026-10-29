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

    def values(self, sid, rng):
        from urllib.parse import quote
        return self._req("GET", f"{API}/{sid}/values/{quote(rng)}").get("values", [])

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
                      ("Market Signals", "markets"), ("Suppliers", "suppliers"), ("Groups", "groups"),
                      ("Deal Calc", "deal_calc"), ("Price Trends", "price_trends"), ("Price Series", "price_series"),
                      ("Commodity Prices", "commodity_prices"), ("Israel", "../israel/items")]:
        full = LEADS / f"{name}_all.csv"
        path = full if full.exists() else LEADS / f"{name}.csv"
        if path.exists():
            out.append((tab, read_csv(path)))
    th = LEADS / "sheet" / "titles_he.csv"
    if th.exists():
        out.append(("Titles HE", read_csv(th)))
    # upcoming tenders: planned notices (prior information notices, procurement plans) sorted by value
    hdr = rows[0] if rows else []
    if "stage" in hdr:
        si, vi = hdr.index("stage"), hdr.index("est_value_usd") if "est_value_usd" in hdr else None
        up = [r for r in rows[1:] if len(r) > si and r[si] == "planned"]
        def _v(r):
            try:
                return float(str(r[vi]).replace(",", "")) if vi is not None else 0
            except ValueError:
                return 0
        up.sort(key=lambda r: -_v(r))
        out.append(("Upcoming", [hdr] + up[:3000]))
    out.append(("Meta", [["key", "value"], ["tenders_updated_utc", time.strftime("%Y-%m-%d %H:%M", time.gmtime())],
                         ["open_tenders", str(len(out[0][1]) - 1)]]))
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
    elif a[:1] == ["batch"]:
        # python -m leads.push batch <spreadsheet id> <requests.json> : Sheets batchUpdate (layout / formatting)
        reqs = json.loads(open(a[2], encoding="utf-8").read())
        for i in range(0, len(reqs), 200):
            sh._req("POST", f"{API}/{a[1]}:batchUpdate", json={"requests": reqs[i:i + 200]})
        print("applied", len(reqs), "requests to", a[1])
    elif a[:1] == ["layout"]:
        # python -m leads.push layout <spreadsheet id> <layout.json> : {"clear": [ranges], "values": [{"range", "rows"}],
        # "requests": [batchUpdate requests]} - values are written USER_ENTERED (formulas work), then formatting
        from urllib.parse import quote
        lay = json.loads(open(a[2], encoding="utf-8").read())
        ids = {x["properties"]["title"]: x["properties"]["sheetId"] for x in sh.meta(a[1])["sheets"]}

        def resolve(o):  # "@sheet:<title>" -> that tab's sheetId
            if isinstance(o, dict):
                return {k: resolve(v) for k, v in o.items()}
            if isinstance(o, list):
                return [resolve(v) for v in o]
            if isinstance(o, str) and o.startswith("@sheet:"):
                return ids[o[7:]]
            return o
        lay = resolve(lay)
        if lay.get("reset"):
            m = sh._req("GET", f"{API}/{a[1]}", params={"fields": "sheets(properties.sheetId,charts.chartId,conditionalFormats,"
                                                                 "bandedRanges.bandedRangeId,protectedRanges.protectedRangeId)"})
            rq = []
            for sht in m.get("sheets", []):
                sid = sht["properties"]["sheetId"]
                if sid not in lay["reset"]:
                    continue
                rq += [{"deleteEmbeddedObject": {"objectId": c["chartId"]}} for c in sht.get("charts", [])]
                rq += [{"deleteConditionalFormatRule": {"sheetId": sid, "index": i}}
                       for i in reversed(range(len(sht.get("conditionalFormats", []))))]
                rq += [{"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}} for b in sht.get("bandedRanges", [])]
                rq += [{"deleteProtectedRange": {"protectedRangeId": p_["protectedRangeId"]}} for p_ in sht.get("protectedRanges", [])]
            if rq:
                sh._req("POST", f"{API}/{a[1]}:batchUpdate", json={"requests": rq})
            print("reset", len(rq), "objects")
        pre = [r for r in lay.get("pre_requests", []) if r.get("addSheet", {}).get("properties", {}).get("title") not in ids]
        if pre:
            sh._req("POST", f"{API}/{a[1]}:batchUpdate", json={"requests": pre})
        if lay.get("clear"):
            sh._req("POST", f"{API}/{a[1]}/values:batchClear", json={"ranges": lay["clear"]})
        vals = lay.get("values", [])
        for i in range(0, len(vals), 40):
            sh._req("POST", f"{API}/{a[1]}/values:batchUpdate",
                    json={"valueInputOption": "USER_ENTERED",
                          "data": [{"range": v["range"], "values": v["rows"]} for v in vals[i:i + 40]]})
        reqs = lay.get("requests", [])
        for i in range(0, len(reqs), 200):
            sh._req("POST", f"{API}/{a[1]}:batchUpdate", json={"requests": reqs[i:i + 200]})
        print("layout applied:", len(lay.get("values", [])), "ranges,", len(reqs), "requests")
    elif a[:1] == ["tab"]:
        n = sh.replace_tab(a[1], a[2], read_csv(a[3]))
        print("wrote", n, "rows to", a[2])


if __name__ == "__main__":
    main()
