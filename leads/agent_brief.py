"""Builds the "Agent Brief" tab in the Leads Engine sheet: a compact, pre-filtered context the scheduled AI agents
read instead of scanning whole tabs of thousands of rows. Runs every morning before the agents (no AI, no tokens).

Sections (column A = section, B.. = fields, header row per section starts with "#"):
  INTEL_30D            Intel items of the last 30 days (for de-duplication)
  BD_30D               BD Agent opportunities of the last 30 days (market + group pairs already covered)
  KEY_ACCOUNTS_DUE     10 Key Accounts to check next (High priority first, oldest "last checked")
  MARKET_SIGNALS_TOP   top 60 Market Signals by signal_score
  REPEAT_BUYERS_60D    repeat buyers expected to tender in the next 60 days
  PURSUITS             opportunity IDs already handled, with recommendation, status and outcome reason
  PARTNERS             countries with a local partner or relationship

  python -m leads.agent_brief
"""
import datetime as dt
import sys

from .push import LEADS_SHEET, Sheets

CUT = 160


def _rows(s, rng):
    v = s.values(LEADS_SHEET, rng)
    if not v:
        return [], []
    h = [x.strip() for x in v[0]]
    return h, [r + [""] * (len(h) - len(r)) for r in v[1:] if any(c.strip() for c in r)]


def _pick(h, r, cols):
    out = []
    for c in cols:
        i = h.index(c) if c in h else None
        val = r[i] if i is not None and i < len(r) else ""
        out.append(val[:CUT] + ("..." if len(val) > CUT else ""))
    return out


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _date(x):
    try:
        return dt.date.fromisoformat(str(x).strip()[:10])
    except ValueError:
        return None


def build(s):
    today = (dt.datetime.utcnow() + dt.timedelta(hours=2)).date()
    d30 = today - dt.timedelta(days=30)
    out = [["section", "brief built (Asia/Jerusalem)", str(today)]]

    def section(name, cols, rows):
        out.append([name, f"# {len(rows)} rows"] + [])
        out.append(["#" + name] + cols)
        out.extend([[name] + r for r in rows])

    h, rows = _rows(s, "'Intel'!A1:P5000")
    cols = ["id", "date", "category", "country", "commodity_group", "headline_en", "signal", "event_date"]
    sel = [_pick(h, r, cols) for r in rows if (_date(r[h.index("date")]) or dt.date.min) >= d30] if h else []
    section("INTEL_30D", cols, sel)

    h, rows = _rows(s, "'BD Agent'!A1:M5000")
    cols = ["date", "priority", "market", "commodity group", "opportunity", "status", "notes"]
    sel = [_pick(h, r, cols) for r in rows if (_date(r[h.index("date")]) or dt.date.min) >= d30] if h else []
    section("BD_30D", cols, sel)

    h, rows = _rows(s, "'Key Accounts'!A1:S1000")
    cols = ["Account", "Country", "Sector", "Primary commodity group", "Official site", "Priority",
            "verified procurement page", "last checked", "latest signal"]
    if h:
        pr = {"High": 0, "Medium": 1, "Low": 2}
        idx = list(range(len(rows)))
        idx.sort(key=lambda i: (pr.get(rows[i][h.index("Priority")], 3),
                                _date(rows[i][h.index("last checked")]) or dt.date.min))
        sel = [[f"row {i + 2}"] + _pick(h, rows[i], cols) for i in idx[:10]]
        section("KEY_ACCOUNTS_DUE", ["sheet_row"] + cols, sel)

    h, rows = _rows(s, "'Market Signals'!A1:P3000")
    cols = ["product", "group", "country", "imports_usd", "growth_pct", "premium_vs_benchmark_pct", "signal_score"]
    if h:
        rows.sort(key=lambda r: -_num(r[h.index("signal_score")]))
        section("MARKET_SIGNALS_TOP", cols, [_pick(h, r, cols) for r in rows[:60]])

    h, rows = _rows(s, "'Repeat Buyers'!A1:P5000")
    cols = ["buyer", "country", "group", "next_expected", "median_award_usd", "awards_12m", "suppliers_in_db", "last_notice"]
    if h:
        d60 = today + dt.timedelta(days=60)
        sel = [r for r in rows if today <= (_date(r[h.index("next_expected")]) or dt.date.min) <= d60]
        sel.sort(key=lambda r: _date(r[h.index("next_expected")]))
        section("REPEAT_BUYERS_60D", cols, [_pick(h, r, cols) for r in sel[:80]])

    h, rows = _rows(s, "'Pursuits'!A1:V2000")
    if h:
        cols = [h[i] for i in (0, 1, 5, 16, 19, 20) if i < len(h)]
        section("PURSUITS", cols, [_pick(h, r, cols) for r in rows])

    h, rows = _rows(s, "'Partners'!A1:F200")
    if h:
        section("PARTNERS", h[:6], [_pick(h, r, h[:6]) for r in rows])
    return out


def main(argv=None):
    s = Sheets()
    rows = build(s)
    n = s.replace_tab(LEADS_SHEET, "Agent Brief", rows, raw=True)
    print(f"agent brief: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
