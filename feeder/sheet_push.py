"""Write the feed straight into the Commodities Tracker sheet (replaces the AI task's IMPORTDATA + copyPaste step).

Same rules as the sheet's Feed_Merge tab:
- a row whose designated benchmark is automated and that has a fresh price in master_stage.csv gets G-P, R, T, U-Y, AA;
- a manual-benchmark row (AA starts with "manual_") or a row with no fresh price keeps its price (G-P, R, T)
  and only gets the registry columns U, V, W, AA and the check price X, Y when present.
Formula columns A, C, F, Q, S, Z are never written. New history rows are appended to History, one line to Log.

  python -m feeder.sheet_push            push data/import/*.csv
  python -m feeder.sheet_push check      only verify access
"""
import csv
import datetime as dt
import sys
from pathlib import Path
from urllib.parse import quote

from leads.push import API, Sheets

SHEET = "1yHBXBVCU3_flqKCQN8HCRYclWyvvX4wXQsQYZtiOaX4"
IMP = Path(__file__).resolve().parent.parent / "data" / "import"
N = 2000
# stage column -> Master column letter
COLS = ["G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "R", "T", "U", "V", "W", "X", "Y", "AA"]


def _read(name):
    with open(IMP / name, encoding="utf-8") as f:
        return list(csv.reader(f))


def _col(rows, i):
    return [r[i] if i < len(r) else "" for r in rows]


def main(argv=None):
    argv = argv or sys.argv[1:]
    s = Sheets()
    if argv and argv[0] == "check":
        print(s.meta(SHEET)["properties"]["title"]); return 0
    stage = _read("master_stage.csv")[1:]
    stage = (stage + [[""] * len(COLS)] * N)[:N]
    cur = s.values(SHEET, f"Master!G2:AA{N + 1}")
    cur = [(r + [""] * 21)[:21] for r in cur] + [[""] * 21] * (N - len(cur))
    # cur index: G=0 .. AA=20
    idx = {c: i for i, c in enumerate(["G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
                                       "U", "V", "W", "X", "Y", "Z", "AA"])}
    out = {c: [] for c in COLS}
    fed = 0
    for k in range(N):
        st = dict(zip(COLS, (stage[k] + [""] * len(COLS))[:len(COLS)]))
        old = {c: cur[k][idx[c]] for c in COLS}
        manual = (st["AA"] or old["AA"]).startswith("manual_")
        if st["I"] and not manual:
            new = dict(st); fed += 1
        else:
            new = dict(old)
            for c in ("U", "V", "W", "AA", "X", "Y"):
                if st[c] != "":
                    new[c] = st[c]
        for c in COLS:
            out[c].append([new[c]])
    blocks = [("G", "P", COLS[:10]), ("R", "R", ["R"]), ("T", "T", ["T"]), ("U", "Y", ["U", "V", "W", "X", "Y"]),
              ("AA", "AA", ["AA"])]
    data = []
    for a, b, cs in blocks:
        vals = [[out[c][k][0] for c in cs] for k in range(N)]
        data.append({"range": f"Master!{a}2:{b}{N + 1}", "values": vals})
    s._req("POST", f"{API}/{SHEET}/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data})

    hist = _read("history_stage.csv")[1:]
    if hist:
        s._req("POST", f"{API}/{SHEET}/values/{quote('History!A:I')}:append",
               params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
               json={"values": [h + [""] for h in hist]})
    now = (dt.datetime.utcnow() + dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    s._req("POST", f"{API}/{SHEET}/values/{quote('Log!A:G')}:append",
           params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
           json={"values": [[now, "ייבוא פיד אוטומטי (GitHub)", N, fed, 0, 0,
                             f"{fed} מחירים מהפיד, {len(hist)} שורות היסטוריה; מדדים ידניים נשמרו"]]})
    print(f"tracker push: {fed} fed rows, {len(hist)} history rows")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        import traceback
        msg = traceback.format_exc()[-900:]
        print(msg)
        try:
            s = Sheets()
            now = (dt.datetime.utcnow() + dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
            s._req("POST", f"{API}/{SHEET}/values/{quote('Log!A:G')}:append",
                   params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                   json={"values": [[now, "ייבוא פיד אוטומטי - שגיאה", "", "", "", 1, msg]]})
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
