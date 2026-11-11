"""Checks an export made by tools/backup_sheets.py: every file against the hash, row count and column count in
manifest.json, one line per tab. Reads local files only; it never contacts or writes to Google Sheets.

  python tools/restore_sheets_check.py <export_dir>

Exit code: 0 every tab matches, 1 something does not (changed, cut, missing or unlisted file, tab not exported).
"""
import hashlib
import json
import os
import sys

MANIFEST = "manifest.json"


def check_tab(d, e):
    """(ok, text) for one manifest entry."""
    if e.get("status") == "absent":
        return True, "absent in the spreadsheet (nothing to check)"
    if e.get("status") != "ok":
        return False, f"not exported: {e.get('error') or e.get('status')}"
    if os.path.basename(e["file"]) != e["file"]:
        return False, "file name in the manifest points outside the export"
    path = os.path.join(d, e["file"])
    if not os.path.isfile(path):
        return False, f"file missing: {e['file']}"
    with open(path, "rb") as f:
        raw = f.read()
    if hashlib.sha256(raw).hexdigest() != e["sha256"]:
        return False, "hash differs from the manifest (file changed or damaged)"
    try:
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    except ValueError:
        return False, "a line is not valid JSON"
    if any(not isinstance(r, list) for r in rows):
        return False, "a line is not a row"
    cols = max((len(r) for r in rows), default=0)
    if len(rows) != e["rows"] or cols != e["cols"]:
        return False, f"{len(rows)} rows x {cols} columns, manifest says {e['rows']} x {e['cols']}"
    return True, f"{len(rows)} rows x {cols} columns, hash matches"


def check(d):
    """[(ok, line)] for the whole export."""
    try:
        with open(os.path.join(d, MANIFEST), encoding="utf-8") as f:
            man = json.load(f)
        tabs = man["tabs"]
    except (OSError, ValueError, KeyError, TypeError):
        return [(False, "FAIL manifest.json is missing or unreadable")]
    out = []
    for e in tabs:
        ok, text = check_tab(d, e)
        out.append((ok, f"{'OK  ' if ok else 'FAIL'} {e.get('sheet')}/{e.get('tab')}: {text}"))
    listed = {e.get("file") for e in tabs} | {MANIFEST}
    for name in sorted(os.listdir(d)):
        if name not in listed:
            out.append((False, f"FAIL {name}: file is not in the manifest"))
    if not any(e.get("status") == "ok" for e in tabs):
        out.append((False, "FAIL the export holds no tab"))
    return out


def main(argv):
    if len(argv) != 1:
        print(__doc__); return 1
    res = check(argv[0])
    for _, line in res:
        print(line)
    bad = sum(not ok for ok, _ in res)
    print(f"export {'is complete' if not bad else 'FAILED the check'}: {len(res) - bad} ok, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
