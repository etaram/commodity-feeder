"""Restore drill: writes an export made by tools/backup_sheets.py into a NEW, EMPTY spreadsheet, reads every tab back
and compares it with the export. It proves that the backup can be restored; it is not the tool that repairs the live
sheets (that stays a manual step that needs the owner's approval, see the runbook).

  python tools/restore_sheets.py <export_dir> --target <spreadsheet id> [--only "Tab A,Tab B"] [--dry-run]

Environment: GOOGLE_SERVICE_ACCOUNT_JSON (the same secret tools/backup_sheets.py uses; the service account must be an
editor of the target spreadsheet), STATE_SHEET_ID (optional: the live state sheet, refused as a target).

Safety, all checked before the first write:
  - the export must pass tools/restore_sheets_check.py (a damaged export is not restored);
  - the target must not be a spreadsheet the backup reads from: the engine and universe sheet ids of leads/push.py,
    STATE_SHEET_ID, and any id that ends with a "sheet_id_suffix" recorded in the manifest (this covers the state
    sheet even when STATE_SHEET_ID is not set here);
  - a tab of the target that has the same name as a tab to restore must be empty. Nothing is ever overwritten or
    cleared: an existing empty tab is filled, a missing tab is created.

Writing: rows go in batches of at most MAX_ROWS rows and MAX_BYTES bytes of request body, with value input RAW, so
nothing is parsed or evaluated: a formula of a hand-kept tab arrives as its text. HTTP 429 and 5xx are retried with a
growing pause.

Verifying: the tab is read back the way the backup read it (same paging, same render option) and compared with the
export file: row count, column count, and a hash made the way the backup makes it (sha256 over one compact JSON array
per row). A byte-identical hash is reported when it happens. It cannot be promised, because the Sheets API drops empty
cells at the end of a row and may answer 5.0 for a 5, so both sides are first normalised in the same way (normalise()
below): an empty cell is "", empty cells at the end of a row and empty rows at the end of a tab are dropped, a number
without a fraction is an integer. Nothing else is changed: text is compared exactly, character for character.

Output: one line per tab (counts, match yes/no) and a summary line. No cell content is ever printed or put in the
report; a difference is reported as a row and column number only. restore_report.json is written into the export dir.
Sheet ids are printed as their last 6 characters.

Exit code: 0 every tab restored and matches, 1 a tab does not match or could not be written, 2 refused or not configured.
"""
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import backup_sheets as B          # noqa: E402
from tools import restore_sheets_check as R   # noqa: E402

MAX_ROWS = 10000         # rows per write request
MAX_BYTES = 2_000_000    # bytes of JSON body per write request (Google's advice is about 2 MB)
MAX_CELLS = 10_000_000   # Google's limit for one spreadsheet
REPORT = "restore_report.json"
NORMALISATION = ("empty cell = \"\"; empty cells at the end of a row and empty rows at the end of a tab dropped; "
                 "a number without a fraction = integer; text compared exactly")


class Refused(Exception):
    """A safety or configuration check failed. Nothing was written."""


class SheetsError(Exception):
    """An API call failed. Carries the HTTP status and Google's short error status only, never the message text."""


def live_ids():
    """Ids of the spreadsheets the backup reads from. They are imported, not typed here again."""
    from leads.push import LEADS_SHEET, UNIVERSE_SHEET
    return {i for i in (LEADS_SHEET, UNIVERSE_SHEET, os.environ.get("STATE_SHEET_ID", "").strip()) if i}


def google_send():
    """The real transport: the signed-in session of leads.push.Sheets (same token and scope as the backup)."""
    from leads.push import API, Sheets
    s = Sheets().s

    def send(method, path, params, body):
        r = s.request(method, API + path, params=params, data=body, timeout=120,
                      headers={"Content-Type": "application/json"} if body is not None else None)
        return r.status_code, r.text
    return send


class Client:
    """The few calls the restore needs. send(method, path, params, body bytes or None) -> (status, text) is injected,
    so the tests run without a network. The pause keeps a run under 60 requests a minute, as in the backup."""
    def __init__(self, send, pause=1.1, sleep=time.sleep, tries=6):
        self.send, self.pause, self.sleep, self.tries = send, pause, sleep, tries

    def _req(self, method, path, params=None, body=None):
        raw = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        status, reason = 0, "no answer"
        for attempt in range(self.tries):
            if self.pause:
                self.sleep(self.pause)
            try:
                status, text = self.send(method, path, params, raw)
            except Exception as x:   # a dropped connection is retried like a 503
                status, text, reason = 0, "", type(x).__name__
            if status == 429 or status >= 500 or status == 0:
                if status:
                    reason = "rate limit" if status == 429 else "server error"
                if attempt + 1 < self.tries:
                    self.sleep(min(60, 2 * 2 ** attempt))   # 2, 4, 8, 16, 32 seconds
                continue
            try:
                data = json.loads(text) if text else {}
            except ValueError:
                data = {}
            if status >= 400:
                err = data.get("error", {}) if isinstance(data, dict) else {}
                raise SheetsError(f"HTTP {status} {err.get('status', '') if isinstance(err, dict) else ''}".strip())
            return data
        raise SheetsError(f"HTTP {status} {reason}: gave up after {self.tries} tries")

    def meta(self, sid):
        """{tab title: (sheetId, rows of the grid, columns of the grid)}"""
        m = self._req("GET", f"/{sid}", params={"fields": "sheets.properties(sheetId,title,gridProperties)"})
        out = {}
        for x in m.get("sheets", []):
            p, g = x["properties"], x["properties"].get("gridProperties", {})
            out[p["title"]] = (p.get("sheetId", 0), g.get("rowCount", 0), g.get("columnCount", 0))
        return out

    def values(self, sid, rng, render):
        """Same signature as backup_sheets.Client.values, so backup_sheets.read_tab reads through this client."""
        return self._req("GET", f"/{sid}/values/{quote(rng, safe='')}", params={"valueRenderOption": render}).get("values", [])

    def add_tab(self, sid, title, rows, cols):
        self._req("POST", f"/{sid}:batchUpdate", body={"requests": [{"addSheet": {"properties": {
            "title": title, "gridProperties": {"rowCount": rows, "columnCount": cols}}}}]})

    def grow_tab(self, sid, sheet_id, rows, cols):
        self._req("POST", f"/{sid}:batchUpdate", body={"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"rowCount": rows, "columnCount": cols}},
            "fields": "gridProperties.rowCount,gridProperties.columnCount"}}]})

    def put(self, sid, rng, rows):
        """RAW: the values are stored as they are, nothing is parsed, so no text can turn into a formula."""
        self._req("PUT", f"/{sid}/values/{quote(rng, safe='')}", params={"valueInputOption": "RAW"}, body={"values": rows})


def norm_cell(c):
    if c is None:
        return ""
    if isinstance(c, float) and not isinstance(c, bool) and c == c and abs(c) < 2 ** 53 and c == int(c):
        return int(c)
    return c


def normalise(rows):
    """The form both sides are brought to before they are compared (see the note at the top of the file)."""
    out = []
    for r in rows:
        r = [norm_cell(c) for c in r]
        while r and r[-1] == "":
            r.pop()
        out.append(r)
    while out and not out[-1]:
        out.pop()
    return out


def content_hash(rows):
    """sha256 over one compact JSON array per line: the bytes backup_sheets.write_rows writes and hashes."""
    h = hashlib.sha256()
    for r in rows:
        h.update((json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    return h.hexdigest()


def same(a, b):
    """Equal value and equal kind: 1 and True, or 1 and "1", are different cells."""
    return type(a) is type(b) and a == b


def first_difference(a, b):
    """(row, column) of the first cell that differs, counted from 1; None when the two are the same. Position only."""
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else []), (b[i] if i < len(b) else [])
        for j in range(max(len(x), len(y))):
            if not same(x[j] if j < len(x) else "", y[j] if j < len(y) else ""):
                return i + 1, j + 1
    return None


def width(rows):
    return max((len(r) for r in rows), default=0)


def batches(rows, max_rows=MAX_ROWS, max_bytes=MAX_BYTES):
    """[(first row number, rows)] with each batch inside both limits. A single row larger than max_bytes goes alone."""
    out, cur, size, start = [], [], 0, 1
    for i, r in enumerate(rows, 1):
        n = len(json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
        if cur and (len(cur) >= max_rows or size + n > max_bytes):
            out.append((start, cur)); cur, size, start = [], 0, i
        cur.append(r); size += n
    if cur:
        out.append((start, cur))
    return out


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f.read().splitlines()]


def load_export(d, only=None, log=print):
    """[(manifest entry, name of the tab in the target, rows)] for the tabs to restore, after the export passed the
    same checks as tools/restore_sheets_check.py. Raises Refused."""
    try:
        os.remove(os.path.join(d, REPORT))   # the report of an earlier drill is not part of the export
    except OSError:
        pass
    res = R.check(d)
    bad = [line for ok, line in res if not ok]
    if bad:
        for line in bad:
            log(line)
        raise Refused(f"the export failed the check ({len(bad)} problems): nothing restored")
    with open(os.path.join(d, R.MANIFEST), encoding="utf-8") as f:
        man = json.load(f)
    entries = [e for e in man["tabs"] if e.get("status") == "ok"]
    if only:
        unknown = [t for t in only if t not in {e["tab"] for e in entries}]
        if unknown:
            raise Refused(f"--only names {len(unknown)} tab(s) that are not in the export: " + ", ".join(unknown))
        entries = [e for e in entries if e["tab"] in only]
    out, used = [], set()
    for e in entries:
        rows = load_rows(os.path.join(d, e["file"]))
        if any(isinstance(c, (list, dict)) for r in rows for c in r):
            raise Refused(f"{e['sheet']}/{e['tab']}: a cell is not a plain value")
        name = e["tab"] if e["tab"] not in used else f"{e['tab']} ({e['sheet']})"   # same tab name in two sheets
        used.add(name)
        out.append((e, name, rows))
    return man, out


def check_target(target, man, ids):
    """Refuses a target that is, or may be, a spreadsheet the backup reads from."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", target or ""):
        raise Refused("--target must be a spreadsheet id (the long part of its address), not a link or a name")
    suffixes = {e.get("sheet_id_suffix") for e in man.get("tabs", [])} - {"", None}
    if target in ids or any(target.endswith(s) for s in suffixes):
        raise Refused("the target is a live spreadsheet the backup reads from: restoring into it is never allowed")


def preflight(client, target, tabs):
    """Reads the target and refuses when a tab to restore already has data there, or when the restore would not fit.
    Returns the target's tabs {title: (sheetId, rows, cols)}."""
    have = client.meta(target)
    full = []
    for _, name, _ in tabs:
        if name in have:
            _, rows, cols = have[name]
            q = name.replace("'", "''")
            got = client.values(target, f"'{q}'!A1:{B.col_letter(max(cols, 1))}{max(rows, 1)}", "FORMULA")
            if any(c not in ("", None) for r in got for c in r):
                full.append(name)
    if full:
        raise Refused(f"the target already has data in {len(full)} tab(s) to restore ({', '.join(full)}): nothing written. "
                      "Use a new empty spreadsheet")
    cells = sum(r * c for _, r, c in have.values()) + sum(max(e["rows"], 1) * max(e["cols"], 1) for e, n, _ in tabs if n not in have)
    if cells > MAX_CELLS:
        raise Refused(f"the restore needs about {cells} cells, more than one spreadsheet holds ({MAX_CELLS}): restore in parts with --only")
    return have


def restore_tab(client, target, have, e, name, rows, clock=time.time):
    """Creates (or sizes) the tab, writes the rows, reads them back, compares. Returns the report entry."""
    t0 = clock()
    want = normalise(rows)
    out = {"tab": e["tab"], "source": e["sheet"], "rows_expected": e["rows"], "rows_restored": 0,
           "cols_expected": e["cols"], "cols_restored": 0, "content_match": False, "byte_identical": False,
           "write_requests": 0, "seconds": 0.0}
    if width(want) != e["cols"]:   # only when the export itself holds empty cells at the end of its widest row
        out["cols_expected_trimmed"] = width(want)
    try:
        need_rows, need_cols = max(len(rows), 1), max(width(rows), 1)
        if name not in have:
            try:
                client.add_tab(target, name, need_rows, need_cols)
            except SheetsError:
                # a retried request may have created the tab before its answer was lost: look before giving up
                if name not in client.meta(target):
                    raise
            have[name] = (None, need_rows, need_cols)
        elif have[name][1] < need_rows or have[name][2] < need_cols:
            sid, r, c = have[name]
            client.grow_tab(target, sid, max(r, need_rows), max(c, need_cols))
            have[name] = (sid, max(r, need_rows), max(c, need_cols))
        q = name.replace("'", "''")
        for start, part in batches(rows):
            client.put(target, f"'{q}'!A{start}", [["" if c is None else c for c in r] for r in part])
            out["write_requests"] += 1
        _, grid_rows, grid_cols = have[name]
        back = B.read_tab(client, target, name, grid_rows, grid_cols, e.get("render") or "UNFORMATTED_VALUE")
        got = normalise(back)
        out["rows_restored"], out["cols_restored"] = len(got), width(got)
        out["byte_identical"] = content_hash(back) == e["sha256"]
        diff = first_difference(want, got)
        out["content_match"] = (diff is None and content_hash(want) == content_hash(got)
                                and len(got) == len(want) == e["rows"] and width(got) == width(want))
        if diff:
            out["first_difference"] = {"row": diff[0], "col": diff[1]}
    except SheetsError as x:
        out["error"] = str(x)
    out["seconds"] = round(clock() - t0, 1)
    return out


def line(r):
    text = (f"{'OK  ' if r['content_match'] else 'FAIL'} {r['source']}/{r['tab']}: rows {r['rows_restored']} of {r['rows_expected']}, "
            f"columns {r['cols_restored']} of {r['cols_expected']}, match {'yes' if r['content_match'] else 'NO'}")
    if r["content_match"]:
        text += " (byte-identical)" if r["byte_identical"] else " (after normalising)"
    if "cols_expected_trimmed" in r:
        text += f"; the export has empty cells at the end of its widest row, {r['cols_expected_trimmed']} columns hold data"
    if r.get("first_difference"):
        text += f"; first difference at row {r['first_difference']['row']}, column {r['first_difference']['col']}"
    if r.get("error"):
        text += f"; {r['error']}"
    return text + f"; {r['write_requests']} write requests, {r['seconds']}s"


def run(export_dir, target, client=None, only=None, dry_run=False, ids=None, log=print, clock=time.time):
    """The whole drill. client is made by the caller (None is allowed for a dry run). Returns (exit code, report)."""
    t0 = clock()
    try:
        man, tabs = load_export(export_dir, only, log)
        check_target(target, man, live_ids() if ids is None else ids)
        if not tabs:
            raise Refused("no tab to restore")
        if dry_run:
            for e, name, rows in tabs:
                log(f"DRY  {e['sheet']}/{e['tab']}: {len(rows)} rows, {width(rows)} columns, {len(batches(rows))} write requests")
            log(f"dry run: {len(tabs)} tabs, {sum(len(r) for _, _, r in tabs)} rows would be written to …{B.suffix(target)}; nothing was sent")
            return 0, None
        have = preflight(client, target, tabs)
    except Refused as x:
        log(f"REFUSED: {x}")
        return 2, None
    except SheetsError as x:
        log(f"REFUSED: the target spreadsheet could not be read ({x}). Is it shared with the service account as editor?")
        return 2, None
    results = []
    for e, name, rows in tabs:
        results.append(restore_tab(client, target, have, e, name, rows, clock))
        log(line(results[-1]))
    ok = sum(r["content_match"] for r in results)
    totals = {"tabs": len(results), "matched": ok, "failed": len(results) - ok,
              "byte_identical": sum(r["byte_identical"] for r in results),
              "rows_expected": sum(r["rows_expected"] for r in results), "rows_restored": sum(r["rows_restored"] for r in results),
              "write_requests": sum(r["write_requests"] for r in results), "seconds": round(clock() - t0, 1)}
    report = {"version": 1, "restored_at": B.now(), "export_made_at": man.get("exported_at", ""), "target_id_suffix": B.suffix(target),
              "comparison": NORMALISATION, "tabs": results, "totals": totals}
    with open(os.path.join(export_dir, REPORT), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    log(f"restore drill {'PASSED' if ok == len(results) else 'FAILED'}: {ok} of {len(results)} tabs match "
        f"({totals['byte_identical']} byte-identical), {totals['rows_restored']} of {totals['rows_expected']} rows, "
        f"{totals['seconds']}s, export of {man.get('exported_at', '?')}, target …{B.suffix(target)}. Compared after normalising: {NORMALISATION}")
    return (0 if ok == len(results) else 1), report


def main(argv):
    args, target, only, dry = [], "", None, False
    it = iter(argv)
    for a in it:
        if a == "--target":
            target = next(it, "").strip()
        elif a == "--only":
            only = [t.strip() for t in next(it, "").split(",") if t.strip()]
        elif a == "--dry-run":
            dry = True
        elif a in ("-h", "--help") or a.startswith("--"):
            print(__doc__); return 2
        else:
            args.append(a)
    if len(args) != 1 or not target:
        print(__doc__); return 2
    client = None
    if not dry:
        if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""):
            print("GOOGLE_SERVICE_ACCOUNT_JSON is not set"); return 2
        try:
            client = Client(google_send())
        except Exception as x:
            print(f"could not sign in to Google: {type(x).__name__}"); return 2
    return run(args[0], target, client, only, dry)[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
