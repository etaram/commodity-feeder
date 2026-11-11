"""Export of the application state kept in Google Sheets: one JSON-lines file per tab plus manifest.json.
Read only: this tool never writes to a spreadsheet. Checked afterwards by tools/restore_sheets_check.py.

  python tools/backup_sheets.py <out_dir> [previous manifest.json]

Environment: GOOGLE_SERVICE_ACCOUNT_JSON (the same secret leads/push.py uses), STATE_SHEET_ID (the small spreadsheet
the app writes its state to, see dealdesk/lib/sheets.ts), BACKUP_REQUIRE_STATE_SHEET=1 (stop when STATE_SHEET_ID is
empty instead of reading the state tabs from the engine sheet), BACKUP_ALLOW_SHRINK ("all" or tab names separated by
commas: tabs allowed to lose rows this run). The engine and universe sheet ids come from leads/push.py.

Which tabs. Only tabs that hold state that cannot be rebuilt from the repository; the collectors' bulk tabs
(Tenders, Awards, Suppliers ... written by leads/push.py replace_tab) are left out on purpose.
  STATE_TABS    copy of STATE_TABS in dealdesk/lib/sheets.ts (tests/test_backup_sheets.py fails when they differ).
                Read from the state sheet; from the engine sheet when STATE_SHEET_ID is not set, as the app does.
  ENGINE_TABS   the other tabs the app appends to in the engine sheet, found by reading every caller of appendRow /
                appendRows / writeRange / append in dealdesk/lib and dealdesk/app (11 Nov 2026):
                Deal Records (lib/deal.ts), Panel Jobs and Pursuits (app/api/panel/append, run, reverse; lib/sheets.ts
                queueJob), Check queue (app/api/panel/company-check), Web Suppliers (app/api/panel/run), Campaigns,
                Campaign Accounts, Suppression, Outreach Log, LinkedIn Tasks (lib/outreach/store.ts; its Outbox tab is
                already in STATE_TABS).
  INPUT_TABS    tabs of the engine sheet kept by hand that the Python jobs read as input (leads/run.py, fta.py,
                briefing.py, archive.py, webpanel.py). Not written by the app; exported as typed (formulas kept) and
                not covered by the half-rows guard, because some of them are views whose length moves.
  UNIVERSE_TABS the two tabs the app appends to in the private supplier universe sheet (lib/verify.ts,
                lib/refineai.ts, app/api/panel/label). The rest of that sheet is collector output.

Exit code: 0 exported, 1 a tab lost more than half its rows since the previous manifest (or disappeared),
2 configuration or API error. The manifest is written in every case. Sheet ids are printed as their last 6 characters.
"""
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATE_TABS = ["Activity", "App Log", "AI Usage", "Telegram Chat", "Telegram", "Agent Runs", "Agent Approvals", "Locks", "Tender Projects", "Tender Watches", "Coverage Cache", "Briefs", "Users", "Profiles", "Push", "Workspace strategy", "Client Dossiers", "Prospects", "My Network", "Assertions", "Decisions", "Outbox", "Missions", "Outcomes", "Send Guard"]
ENGINE_TABS = ["Deal Records", "Panel Jobs", "Pursuits", "Check queue", "Web Suppliers",
               "Campaigns", "Campaign Accounts", "Suppression", "Outreach Log", "LinkedIn Tasks"]
INPUT_TABS = ["Pipeline", "Contacts", "Projects", "Project Tasks", "Partners", "Profile", "Assumptions", "Briefing Sources"]
UNIVERSE_TABS = ["Verified capabilities", "Refine AI"]

PAGE_ROWS = 1000   # rows per request: some tabs hold cells of 45,000 characters, so a page stays a few megabytes
MANIFEST = "manifest.json"


def col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


def suffix(sid):
    return sid[-6:] if sid else ""


def file_name(group, tab):
    return f"{group}__{re.sub(r'[^A-Za-z0-9]+', '_', tab).strip('_')}.jsonl"


def plan(state_id, engine_id, universe_id):
    """[(group, sheet id, tab, render, guarded)] in export order. Group names the spreadsheet in file names."""
    out = [("state" if state_id else "engine", state_id or engine_id, t, "UNFORMATTED_VALUE", True) for t in STATE_TABS]
    out += [("engine", engine_id, t, "UNFORMATTED_VALUE", True) for t in ENGINE_TABS]
    out += [("engine", engine_id, t, "FORMULA", False) for t in INPUT_TABS]
    out += [("universe", universe_id, t, "UNFORMATTED_VALUE", True) for t in UNIVERSE_TABS]
    return out


class Client:
    """The two reads the export needs, on top of leads.push.Sheets (its token, retries and timeouts)."""
    def __init__(self, pause=1.1):
        from leads.push import API, Sheets
        self.api, self.sh, self.pause = API, Sheets(), pause   # the pause keeps a run under 60 reads a minute

    def grids(self, sid):
        m = self.sh._req("GET", f"{self.api}/{sid}", params={"fields": "sheets.properties(title,gridProperties)"})
        return {x["properties"]["title"]: (x["properties"].get("gridProperties", {}).get("rowCount", 0),
                                           x["properties"].get("gridProperties", {}).get("columnCount", 0)) for x in m.get("sheets", [])}

    def values(self, sid, rng, render):
        from urllib.parse import quote
        time.sleep(self.pause)
        return self.sh._req("GET", f"{self.api}/{sid}/values/{quote(rng)}", params={"valueRenderOption": render}).get("values", [])


def read_tab(client, sid, tab, grid_rows, grid_cols, render, page=PAGE_ROWS):
    """Every row of a tab, read a page at a time. The API drops empty rows at the end of each answer, so a short page
    is not the end of the tab: the rest of the grid is asked for once, and paging goes on only when it holds data.
    Rows keep their position (an empty row inside the data stays an empty row); empty rows at the end are dropped."""
    q, last = tab.replace("'", "''"), col_letter(max(grid_cols, 1))
    rows, start = [], 1
    while start <= grid_rows:
        end = min(start + page - 1, grid_rows)
        got = client.values(sid, f"'{q}'!A{start}:{last}{end}", render)
        rows += [[] for _ in range(start - 1 - len(rows))] + got
        start = end + 1
        if len(got) < page and start <= grid_rows and not client.values(sid, f"'{q}'!A{start}:{last}{grid_rows}", render):
            break
    while rows and not any(c not in ("", None) for c in rows[-1]):
        rows.pop()
    return rows


def write_rows(path, rows):
    """One JSON array per line. Returns (rows, columns, sha256 of the file)."""
    h = hashlib.sha256()
    with open(path, "wb") as f:
        for r in rows:
            b = (json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            f.write(b); h.update(b)
    return len(rows), max((len(r) for r in rows), default=0), h.hexdigest()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def export(client, tabs, out_dir, page=PAGE_ROWS, log=print):
    """Writes the files and manifest.json; returns the manifest. A tab that is not in its spreadsheet is recorded as
    absent; a tab that cannot be read is recorded as error (the other tabs are still exported)."""
    os.makedirs(out_dir, exist_ok=True)
    ids = {sid for _, sid, _, _, _ in tabs}
    clean = lambda e: re.sub("|".join(re.escape(i) for i in ids if i) or "$^", lambda m: "…" + suffix(m.group()), str(e))[:200]
    grids, entries = {}, []
    for group, sid, tab, render, guarded in tabs:
        e = {"sheet": group, "sheet_id_suffix": suffix(sid), "tab": tab, "status": "ok", "file": "", "rows": 0, "cols": 0,
             "sha256": "", "render": render, "guarded": guarded, "exported_at": now()}
        try:
            if sid not in grids:
                grids[sid] = client.grids(sid)
            if tab not in grids[sid]:
                e["status"] = "absent"
            else:
                rows = read_tab(client, sid, tab, *grids[sid][tab], render, page)
                e["file"] = file_name(group, tab)
                e["rows"], e["cols"], e["sha256"] = write_rows(os.path.join(out_dir, e["file"]), rows)
        except Exception as x:  # one unreadable tab must not hide the others; the run still ends with an error
            e["status"], e["error"] = "error", clean(x)
        entries.append(e)
        log(f"{e['status']:6} {group}/{tab}: {e['rows']} rows, {e['cols']} columns" + (f" ({e['error']})" if e.get("error") else ""))
    man = {"version": 1, "exported_at": now(), "tabs": entries}
    with open(os.path.join(out_dir, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    return man


def shrunk(prev, cur, allow=()):
    """Guarded tabs that were exported last time and now have fewer than half the rows (absent or unreadable = 0 rows).
    The guard against saving a wiped sheet as if it were a good backup. allow: tab names, or "all"."""
    if "all" in allow:
        return []
    have = {(e["sheet"], e["tab"]): e for e in cur.get("tabs", [])}
    out = []
    for p in prev.get("tabs", []):
        if p.get("status") != "ok" or not p.get("guarded", True) or p["tab"] in allow:
            continue
        c = have.get((p["sheet"], p["tab"]))
        n = c["rows"] if c and c["status"] == "ok" else 0
        if n * 2 < p["rows"]:
            out.append(f"{p['sheet']}/{p['tab']}: {p['rows']} rows before, {n} now")
    return out


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 2
    out_dir, prev_path = argv[0], (argv[1] if len(argv) > 1 else "")
    state = os.environ.get("STATE_SHEET_ID", "").strip()
    if not state and os.environ.get("BACKUP_REQUIRE_STATE_SHEET", "").strip() not in ("", "0"):
        print("STATE_SHEET_ID is not set: stopping, because the state tabs of the engine sheet may be old copies"); return 2
    if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""):
        print("GOOGLE_SERVICE_ACCOUNT_JSON is not set"); return 2
    from leads.push import LEADS_SHEET, UNIVERSE_SHEET
    try:
        client = Client()
    except Exception as x:
        print(f"could not sign in to Google: {type(x).__name__}"); return 2
    man = export(client, plan(state, LEADS_SHEET, UNIVERSE_SHEET), out_dir)
    t = man["tabs"]
    print(f"exported {sum(e['status'] == 'ok' for e in t)} tabs, {sum(e['rows'] for e in t)} rows; "
          f"absent {sum(e['status'] == 'absent' for e in t)}; errors {sum(e['status'] == 'error' for e in t)}")
    code = 2 if any(e["status"] == "error" for e in t) else 0
    if prev_path and os.path.exists(prev_path) and os.path.getsize(prev_path):
        with open(prev_path, encoding="utf-8") as f:
            prev = json.load(f)
        allow = [a.strip() for a in os.environ.get("BACKUP_ALLOW_SHRINK", "").split(",") if a.strip()]
        bad = shrunk(prev, man, allow)
        for b in bad:
            print("SHRUNK", b)
        if bad:
            print("stopping: this export must not replace the previous backup (set BACKUP_ALLOW_SHRINK when the loss is intended)")
            code = code or 1
    else:
        print("no previous manifest: the half-rows guard did not run")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
