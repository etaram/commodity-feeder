"""Leads Engine design v3: one visual system for the whole workbook (English, left to right).

  python tools/sheet_layout/design.py            -> tools/sheet_layout/design.json
  python -m leads.push layout <sheet id> tools/sheet_layout/design.json

Front screens (Home, Search, Deals, Markets, Israel Overview, Commodities, Buyers, Guide) get a title bar, a linked
navigation bar, KPI cards, charts and section cards. Work tables and raw data tabs get a styled header, frozen header,
filters, number formats and banding; raw data tabs are protected (warning only) against accidental edits.
Re-running is safe: charts, conditional formats, bandings and protections of these tabs are reset first."""
import json
from pathlib import Path

FONT = "Inter"
C = {"navy": "0B1B33", "blue": "1E3A5F", "accent": "2F6FB3", "light": "E6ECF3", "card": "F4F7FA", "line": "D5DDE7",
     "text": "1C2733", "muted": "667385", "white": "FFFFFF", "green": "0B7A4B", "green_bg": "DDF3E7", "amber": "8A5300",
     "amber_bg": "FFF0D1", "red": "B42318", "red_bg": "FDE7E5", "gray_bg": "EEF0F3", "yellow": "FFF7D6", "teal": "0E7C86",
     "gray_tab": "8A94A6", "amber_tab": "C27C0E", "black": "000000"}
G = {"Home": 45, "Search": 31, "Pipeline": 47, "Pursuits": 24, "Quotes": 28, "Deals": 50, "Markets": 48, "Israel": 49, "USA": 57,
     "Commodities": 51, "Buyers": 52, "Intel": 29, "Guide": 25}
NAV = ["Home", "Search", "Pipeline", "Pursuits", "Deals", "Markets", "Israel", "USA", "Commodities", "Buyers", "Intel", "Guide"]
values, req, clear, reset = [], [], [], []
_chart_id = [900000]


def rgb(h):
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def col(c):
    s = ""
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def rng(sid, r1, r2, c1, c2):
    """r2 = 0 means 'to the last row' (raw tabs grow and shrink)."""
    out = {"sheetId": sid, "startRowIndex": r1 - 1, "startColumnIndex": c1 - 1, "endColumnIndex": c2}
    if r2:
        out["endRowIndex"] = r2
    return out


def fmt(r, f, fields):
    req.append({"repeatCell": {"range": r, "cell": {"userEnteredFormat": f}, "fields": fields}})


def put(tab, r, c, rows):
    values.append({"range": f"'{tab}'!{col(c)}{r}", "rows": rows})


def widths(sid, ws):
    for i, w in enumerate(ws):
        req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                                  "properties": {"pixelSize": w, "hiddenByUser": w <= 2}, "fields": "pixelSize,hiddenByUser"}})


def heights(sid, r1, r2, h):
    req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": r1 - 1, "endIndex": r2},
                                              "properties": {"pixelSize": h}, "fields": "pixelSize"}})


def merge(sid, r, c1, c2, r2=None):
    req.append({"mergeCells": {"range": rng(sid, r, r2 or r, c1, c2), "mergeType": "MERGE_ALL"}})


def text(color, size=10, bold=False, italic=False):
    return {"fontFamily": FONT, "fontSize": size, "bold": bold, "italic": italic, "foregroundColorStyle": {"rgbColor": rgb(C[color])}}


def numfmt(sid, r1, r2, c1, c2, pat, typ="NUMBER"):
    fmt(rng(sid, r1, r2, c1, c2), {"numberFormat": {"type": typ, "pattern": pat}}, "userEnteredFormat.numberFormat")


USD, PCT, PCT1, INT, DATE, DDMM = ("CURRENCY", "$#,##0"), ("PERCENT", "0%"), ("PERCENT", "0.0%"), ("NUMBER", "#,##0"), \
    ("DATE", "dd mmm yyyy"), ("DATE", "dd mmm")
PCTV = ("NUMBER", '+0.0"%";-0.0"%";0.0"%"')


def nf(sid, r1, r2, c1, c2, f):
    numfmt(sid, r1, r2, c1, c2, f[1], f[0])


def chip(ranges, value, fg, bg, kind="TEXT_EQ"):
    req.append({"addConditionalFormatRule": {"rule": {"ranges": ranges, "booleanRule": {
        "condition": {"type": kind, "values": [{"userEnteredValue": value}]},
        "format": {"backgroundColorStyle": {"rgbColor": rgb(C[bg])}, "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": rgb(C[fg])}}}}},
        "index": 0}})


def decision_chips(ranges):
    chip(ranges, "Pursue", "green", "green_bg"); chip(ranges, "Watch", "amber", "amber_bg"); chip(ranges, "Ignore", "muted", "gray_bg")


# ------------------------------------------------------------------ screen frame
def screen(tab, sid, ncols, ws, title, subtitle, rows=140):
    reset.append(sid)
    clear.append(f"'{tab}'!A1:Z{rows}")
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "rightToLeft": False, "gridProperties": {
        "hideGridlines": True, "rowCount": rows, "columnCount": ncols, "frozenRowCount": 3, "frozenColumnCount": 0}},
        "fields": "rightToLeft,gridProperties(hideGridlines,rowCount,columnCount,frozenRowCount,frozenColumnCount)"}})
    req.append({"unmergeCells": {"range": rng(sid, 1, rows, 1, ncols)}})
    fmt(rng(sid, 1, rows, 1, ncols), {"wrapStrategy": "CLIP", "verticalAlignment": "MIDDLE", "horizontalAlignment": "LEFT",
                                      "backgroundColorStyle": {"rgbColor": rgb(C["white"])}, "textFormat": text("text"),
                                      "padding": {"left": 6, "right": 6}, "borders": {}},
        "userEnteredFormat")
    widths(sid, ws)
    heights(sid, 1, rows, 24)
    put(tab, 1, 1, [[title]]); put(tab, 2, 1, [[subtitle]])
    merge(sid, 1, 1, ncols); merge(sid, 2, 1, ncols); merge(sid, 3, 1, ncols)
    fmt(rng(sid, 1, 1, 1, ncols), {"backgroundColorStyle": {"rgbColor": rgb(C["navy"])}, "textFormat": text("white", 18, True),
                                   "padding": {"left": 16}}, "userEnteredFormat(backgroundColorStyle,textFormat,padding)")
    fmt(rng(sid, 2, 2, 1, ncols), {"backgroundColorStyle": {"rgbColor": rgb(C["navy"])}, "textFormat": text("light", 10, False, True),
                                   "padding": {"left": 16}}, "userEnteredFormat(backgroundColorStyle,textFormat,padding)")
    heights(sid, 1, 1, 50); heights(sid, 2, 2, 26); heights(sid, 3, 3, 32)
    nav_bar(sid, tab)


def nav_bar(sid, current):
    label, runs = "", []
    for name in NAV:
        start = len(label)
        label += name
        cur = (name == current) or (name == "Israel" and current == "Israel Overview")
        runs.append({"startIndex": start, "format": {"link": {"uri": f"#gid={G[name]}"}, "underline": False, "bold": cur,
                                                     "foregroundColorStyle": {"rgbColor": rgb(C["white"] if cur else C["light"])}}})
        if name != NAV[-1]:
            runs.append({"startIndex": len(label), "format": {"foregroundColorStyle": {"rgbColor": rgb(C["accent"])}, "bold": False}})
            label += "     |     "
    req.append({"updateCells": {"range": rng(sid, 3, 3, 1, 1), "rows": [{"values": [{
        "userEnteredValue": {"stringValue": label}, "textFormatRuns": runs,
        "userEnteredFormat": {"backgroundColorStyle": {"rgbColor": rgb(C["blue"])}, "textFormat": text("light", 10),
                              "padding": {"left": 16}, "verticalAlignment": "MIDDLE"}}]}],
        "fields": "userEnteredValue,textFormatRuns,userEnteredFormat"}})


def kpis(tab, sid, row, items, span=2):
    for i, (label, formula, f) in enumerate(items):
        c = 1 + span * i
        put(tab, row, c, [[label]]); put(tab, row + 1, c, [[formula]])
        merge(sid, row, c, c + span - 1); merge(sid, row + 1, c, c + span - 1)
        nf(sid, row + 1, row + 1, c, c + span - 1, f)
    n = span * len(items)
    fmt(rng(sid, row, row, 1, n), {"backgroundColorStyle": {"rgbColor": rgb(C["card"])}, "horizontalAlignment": "CENTER",
                                   "verticalAlignment": "BOTTOM", "textFormat": text("muted", 9, True)},
        "userEnteredFormat(backgroundColorStyle,horizontalAlignment,verticalAlignment,textFormat)")
    fmt(rng(sid, row + 1, row + 1, 1, n), {"backgroundColorStyle": {"rgbColor": rgb(C["card"])}, "horizontalAlignment": "CENTER",
                                           "verticalAlignment": "MIDDLE", "textFormat": text("navy", 22, True)},
        "userEnteredFormat(backgroundColorStyle,horizontalAlignment,verticalAlignment,textFormat)")
    heights(sid, row, row, 26); heights(sid, row + 1, row + 1, 48)
    for i in range(len(items)):
        c = 1 + span * i
        req.append({"updateBorders": {"range": rng(sid, row, row + 1, c, c + span - 1),
                                      "top": {"style": "SOLID_THICK", "colorStyle": {"rgbColor": rgb(C["accent"])}},
                                      "left": {"style": "SOLID_THICK", "colorStyle": {"rgbColor": rgb(C["white"])}},
                                      "right": {"style": "SOLID_THICK", "colorStyle": {"rgbColor": rgb(C["white"])}}}})


def section(tab, sid, row, c1, c2, title):
    put(tab, row, c1, [[title]])
    merge(sid, row, c1, c2)
    fmt(rng(sid, row, row, c1, c2), {"backgroundColorStyle": {"rgbColor": rgb(C["white"])}, "textFormat": text("navy", 12, True),
                                     "verticalAlignment": "BOTTOM", "padding": {"left": 4},
                                     "borders": {"bottom": {"style": "SOLID_MEDIUM", "colorStyle": {"rgbColor": rgb(C["accent"])}}}},
        "userEnteredFormat(backgroundColorStyle,textFormat,verticalAlignment,padding,borders)")
    heights(sid, row, row, 34)


def table_header(sid, row, c1, c2, labels=None, tab=None):
    if labels:
        put(tab, row, c1, [labels])
    fmt(rng(sid, row, row, c1, c2), {"backgroundColorStyle": {"rgbColor": rgb(C["light"])}, "textFormat": text("blue", 9, True),
                                     "verticalAlignment": "MIDDLE"},
        "userEnteredFormat(backgroundColorStyle,textFormat,verticalAlignment)")
    heights(sid, row, row, 28)


def rows_style(sid, r1, r2, c1, c2):
    req.append({"updateBorders": {"range": rng(sid, r1, r2, c1, c2),
                                  "innerHorizontal": {"style": "SOLID", "colorStyle": {"rgbColor": rgb(C["line"])}},
                                  "bottom": {"style": "SOLID", "colorStyle": {"rgbColor": rgb(C["line"])}}}})


def bars(tab, sid, r1, r2, value_col, bar_col, color="accent"):
    """In-cell bar chart for each row (SPARKLINE)."""
    vc = col(value_col)
    put(tab, r1, bar_col, [[f'=IF(OR({vc}{r}="",NOT(ISNUMBER({vc}{r}))),"",SPARKLINE({vc}{r},{{"charttype","bar";"max",MAX(${vc}${r1}:${vc}${r2});"color1","#{C[color]}"}}))']
                           for r in range(r1, r2 + 1)])


def chart(sid, title, dom, ser, anchor_row, anchor_col, w, h, kind="BAR", color="accent", series_name=""):
    _chart_id[0] += 1
    req.append({"addChart": {"chart": {"chartId": _chart_id[0], "spec": {
        "title": title, "titleTextFormat": text("navy", 12, True), "fontName": FONT,
        "backgroundColorStyle": {"rgbColor": rgb(C["white"])},
        "basicChart": {"chartType": kind, "legendPosition": "NO_LEGEND", "headerCount": 0,
                       "axis": [{"position": "BOTTOM_AXIS", "format": text("muted", 9)}, {"position": "LEFT_AXIS", "format": text("muted", 9)}],
                       "domains": [{"domain": {"sourceRange": {"sources": [dom]}}}],
                       "series": [{"series": {"sourceRange": {"sources": [ser]}}, "targetAxis": "BOTTOM_AXIS" if kind == "BAR" else "LEFT_AXIS",
                                   "colorStyle": {"rgbColor": rgb(C[color])}}]}},
        "position": {"overlayPosition": {"anchorCell": {"sheetId": sid, "rowIndex": anchor_row - 1, "columnIndex": anchor_col - 1},
                                         "offsetXPixels": 6, "offsetYPixels": 6, "widthPixels": w, "heightPixels": h}}}}})


T, IL, DC, PT, PS, CP, RB = "Tenders", "Israel", "'Deal Calc'", "'Price Trends'", "'Price Series'", "'Commodity Prices'", "'Repeat Buyers'"

# ================================================================== HOME
S, tab = 45, "Home"
screen(tab, S, 10, [90, 360, 230, 140, 120, 100, 110, 130, 110, 230], "Sinder Opportunity Engine",
       "Tenders from 30 international sources and ~1,000 Israeli public bodies, ranked by a deal calculation, with research agents on top.")
kpis(tab, S, 5, [("PURSUE NOW", f'=COUNTIF({T}!T2:T,"Pursue")', INT),
                 ("EXPECTED VALUE OF PURSUE LIST", f'=SUMIF({DC}!B2:B,"Pursue",{DC}!C2:C)', USD),
                 ("ISRAEL: OPEN NOTICES", f"=COUNTA({IL}!O2:O)", INT),
                 ("ISRAEL: NEW IN 48H", f'=COUNTIF({IL}!B2:B,"NEW")', INT),
                 ("OPEN TENDERS WORLDWIDE", f"=COUNTA({T}!S2:S)", INT)])
put(tab, 7, 1, [['="Updated "&IFERROR(Meta!B2,"-")&" UTC. Israel scanned daily, world tenders every 4 hours, agents every morning."']])
merge(S, 7, 1, 10); fmt(rng(S, 7, 7, 1, 10), {"textFormat": text("muted", 9, False, True), "horizontalAlignment": "RIGHT"},
                        "userEnteredFormat(textFormat,horizontalAlignment)")
sec = [
    (9, "Best deals now - ranked by priority value", ["Country", "Opportunity", "Buyer", "Route", "Deal value", "Net margin", "Win prob.", "Expected value", "Deadline", "Link"], 12,
     f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{DC}!S2:S,{DC}!W2:W,{DC}!V2:V,{DC}!AC2:AC,{DC}!F2:F,{DC}!L2:L,{DC}!E2:E,{DC}!C2:C,{DC}!X2:X,{DC}!Y2:Y,{DC}!AE2:AE}},{DC}!B2:B="Pursue",({DC}!AA2:AA="")+({DC}!AA2:AA>=5)),11,FALSE),12,10),"Waiting for the next data refresh")'),
    (24, "Israel - newest notices from public bodies", ["New", "First seen", "Published by", "Type", "Title (Hebrew)", "Kind", "Deadline", "Days left", "Sector", "Link"], 15,
     f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{IL}!B2:B,{IL}!A2:A,{IL}!C2:C,{IL}!D2:D,{IL}!H2:H,{IL}!F2:F,{IL}!I2:I,{IL}!J2:J,{IL}!L2:L,{IL}!M2:M}},{IL}!O2:O<>"",{IL}!F2:F<>"exemption"),2,FALSE),15,10),"Waiting for the first Israel scan")'),
    (42, "Upcoming tenders - announced, not yet open", ["Country", "Tender", "Buyer", "Value (USD)", "Sector", "Decision", "Link"], 8,
     '=IFERROR(ARRAY_CONSTRAIN({Upcoming!G2:G,Upcoming!J2:J,Upcoming!I2:I,Upcoming!K2:K,Upcoming!F2:F,Upcoming!T2:T,Upcoming!P2:P},8,7),"No upcoming tenders")'),
    (53, "Market intelligence - official and tier-1 sources", ["Date", "Region", "Country", "Headline", "What it means for Sinder", "Signal", "Source", "Link"], 8,
     '=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({Intel!B2:B,Intel!D2:D,Intel!E2:E,Intel!G2:G,Intel!I2:I,Intel!K2:K,Intel!M2:M,Intel!O2:O},Intel!A2:A<>""),1,FALSE),8,8),"No items yet")'),
    (64, "Repeat buyers expected to buy in the next 60 days", ["Buyer", "Country", "Commodity group", "Awards (12m)", "Next expected", "Current suppliers", "Buyer email"], 10,
     f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{RB}!A2:A,{RB}!B2:B,{RB}!C2:C,{RB}!D2:D,{RB}!H2:H,{RB}!I2:I,{RB}!K2:K}},{RB}!H2:H>=TODAY(),{RB}!H2:H<=TODAY()+60),5,TRUE),10,7),"None in the next 60 days")'),
    (77, "Latest results from the research worker", ["Updated", "Type", "Subject", "Result (first lines)", "Link"], 8,
     "=ARRAYFORMULA(IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({'Panel Jobs'!K2:K,'Panel Jobs'!C2:C,'Panel Jobs'!E2:E,LEFT('Panel Jobs'!I2:I,400),'Panel Jobs'!J2:J},'Panel Jobs'!H2:H=\"done\"),1,FALSE),8,5),\"No results yet\"))"),
]
for r, title, hdr, n, formula in sec:
    section(tab, S, r, 1, 10, title)
    table_header(S, r + 1, 1, len(hdr), hdr, tab)
    put(tab, r + 2, 1, [[formula]])
    rows_style(S, r + 2, r + 1 + n, 1, len(hdr))
nf(S, 11, 22, 5, 5, USD); nf(S, 11, 22, 6, 6, PCT1); nf(S, 11, 22, 7, 7, PCT); nf(S, 11, 22, 8, 8, USD); nf(S, 11, 22, 9, 9, DATE)
fmt(rng(S, 11, 22, 8, 8), {"textFormat": text("green", 10, True)}, "userEnteredFormat.textFormat")
nf(S, 26, 40, 2, 2, DDMM); nf(S, 26, 40, 7, 7, DATE); nf(S, 44, 51, 4, 4, USD); nf(S, 55, 62, 1, 1, DDMM); nf(S, 66, 75, 5, 5, DATE)
fmt(rng(S, 26, 40, 5, 5), {"horizontalAlignment": "RIGHT"}, "userEnteredFormat.horizontalAlignment")
chip([rng(S, 26, 40, 1, 1)], "NEW", "green", "green_bg"); chip([rng(S, 26, 40, 8, 8)], "7", "red", "red_bg", "NUMBER_LESS")
decision_chips([rng(S, 44, 51, 6, 6)]); chip([rng(S, 55, 62, 6, 6)], "High", "amber", "amber_bg")
chip([rng(S, 11, 22, 4, 4)], "via local partner", "accent", "light"); chip([rng(S, 11, 22, 4, 4)], "needs local partner", "amber", "amber_bg")

# ================================================================== SEARCH
S, tab = 31, "Search"
screen(tab, S, 13, [230, 430, 220, 200, 110, 100, 70, 60, 95, 80, 150, 220, 150], "Tender search",
       "Type keywords in English or Hebrew and pick filters. Results update instantly, best fit first (Israel is weighted first).", rows=1100)
labels = ["Keywords (comma separated)", "Sector", "Region", "Country (ISO3, e.g. ISR, USA, KEN)", "Decision", "Min. days to deadline"]
put(tab, 5, 1, [[x] for x in labels])
put(tab, 10, 2, [["7"]]) if False else None
fmt(rng(S, 5, 10, 1, 1), {"textFormat": text("blue", 10, True), "backgroundColorStyle": {"rgbColor": rgb(C["card"])}},
    "userEnteredFormat(textFormat,backgroundColorStyle)")
fmt(rng(S, 5, 10, 2, 2), {"backgroundColorStyle": {"rgbColor": rgb(C["yellow"])}, "textFormat": text("text", 11, True),
                          "borders": {"bottom": {"style": "SOLID", "colorStyle": {"rgbColor": rgb(C["line"])}}}},
    "userEnteredFormat(backgroundColorStyle,textFormat,borders)")
heights(S, 5, 10, 30)
put(tab, 5, 4, [["Results"]]); put(tab, 6, 4, [['=IF(A13="No results",0,COUNTA(A13:A))']])
fmt(rng(S, 5, 5, 4, 4), {"textFormat": text("muted", 9, True), "horizontalAlignment": "CENTER", "backgroundColorStyle": {"rgbColor": rgb(C["card"])}},
    "userEnteredFormat(textFormat,horizontalAlignment,backgroundColorStyle)")
fmt(rng(S, 6, 7, 4, 4), {"textFormat": text("navy", 22, True), "horizontalAlignment": "CENTER", "backgroundColorStyle": {"rgbColor": rgb(C["card"])}},
    "userEnteredFormat(textFormat,horizontalAlignment,backgroundColorStyle)")
merge(S, 6, 4, 4, 7)
put(tab, 11, 1, [["Examples: tuna, sulphur, cement, steel pipes, מכרז אספקה. Leave a field empty to ignore it."]])
merge(S, 11, 1, 6); fmt(rng(S, 11, 11, 1, 6), {"textFormat": text("muted", 9, False, True)}, "userEnteredFormat.textFormat")
for r, (lst_col, n) in ((6, ("T", 60)), (7, ("U", 30)), (9, ("V", 10))):
    req.append({"setDataValidation": {"range": rng(S, r, r, 2, 2), "rule": {"condition": {"type": "ONE_OF_RANGE",
               "values": [{"userEnteredValue": f"=Lists!${lst_col}$1:${lst_col}${n}"}]}, "showCustomUi": True, "strict": False}}})
table_header(S, 12, 1, 13, ["Country", "Tender", "Buyer", "Sector", "Value (USD)", "Deadline", "Days left", "Fit", "Competition",
                            "Decision", "Source", "Link", "ID"], tab)
put(tab, 13, 1, [["=IFERROR(ARRAYFORMULA(LET(T,Tenders!A2:AE,id,INDEX(T,,19),heraw,IFERROR(VLOOKUP(id,'Titles HE'!A:B,2,FALSE),\"\"),"
                  "txt,LOWER(INDEX(T,,10)&\" \"&INDEX(T,,9)&\" \"&INDEX(T,,17)&\" \"&INDEX(T,,18)&\" \"&INDEX(T,,6)&\" \"&heraw),"
                  "re,\"(?:^|[^a-z0-9\\x{00c0}-\\x{024f}\\x{0400}-\\x{04ff}\\x{0590}-\\x{05ff}])(?:\"&REGEXREPLACE(LOWER(TRIM($B$5)),\"\\s*,\\s*\",\"|\")&\")\","
                  "b,N(INDEX(T,,23))+(INDEX(T,,27)<>\"\"),comp,IF(INDEX(T,,23)=\"\",\"\",IF(b<=2,\"Low\",IF(b<=4,\"Medium\",IF(b<=7,\"High\",\"Very high\")))),"
                  "out,HSTACK(INDEX(T,,7),INDEX(T,,10),INDEX(T,,9),INDEX(T,,6),INDEX(T,,11),INDEX(T,,3),INDEX(T,,4),INDEX(T,,29),comp,INDEX(T,,20),INDEX(T,,12),INDEX(T,,16),id),"
                  "c,(id<>\"\")*REGEXMATCH(txt,re)*(($B$6=\"\")+(INDEX(T,,6)=$B$6))*(($B$7=\"\")+(INDEX(T,,8)=$B$7))*(($B$8=\"\")+(INDEX(T,,7)=UPPER(TRIM($B$8))))"
                  "*(($B$9=\"\")+(INDEX(T,,20)=$B$9))*(($B$10=\"\")+(N(INDEX(T,,4))>=$B$10)),ARRAY_CONSTRAIN(SORT(FILTER(out,c>0),8,FALSE),1000,13))),\"No results\")"]])
put(tab, 10, 2, [["7"]])
nf(S, 13, 1013, 5, 5, USD); nf(S, 13, 1013, 6, 6, DATE)
decision_chips([rng(S, 13, 1013, 10, 10)])
chip([rng(S, 13, 1013, 9, 9)], "Low", "green", "green_bg"); chip([rng(S, 13, 1013, 9, 9)], "Very high", "red", "red_bg")
rows_style(S, 13, 112, 1, 13)
values[:] = [v for v in values if v is not None]

# hidden helper lists for dropdowns
LISTS = 56
req.append({"updateSheetProperties": {"properties": {"sheetId": LISTS, "hidden": True}, "fields": "hidden"}})
put("Lists", 1, 20, [['=SORT(UNIQUE(FILTER(Tenders!F2:F,Tenders!F2:F<>"")))', '=SORT(UNIQUE(FILTER(Tenders!H2:H,Tenders!H2:H<>"")))',
                      '=SORT(UNIQUE(FILTER(Tenders!T2:T,Tenders!T2:T<>"")))']])

# ================================================================== analysis screens
def analysis(tab, sid, ncols, ws, title, subtitle, kp, rows=140):
    screen(tab, sid, ncols, ws, title, subtitle, rows)
    kpis(tab, sid, 5, kp)


# ---- Markets
S, tab = 48, "Markets"
analysis(tab, S, 11, [240, 110, 150, 150, 150, 30, 240, 90, 2, 110, 110],
         "Markets", "Where the open tenders are: by region, sector and source. Refreshed every 4 hours.",
         [("OPEN TENDERS", f"=COUNTA({T}!S2:S)", INT), ("PURSUE", f'=COUNTIF({T}!T2:T,"Pursue")', INT),
          ("COUNTRIES", f"=COUNTUNIQUE({T}!G2:G)", INT), ("CLOSING IN 14 DAYS", f'=COUNTIFS({T}!D2:D,">=0",{T}!D2:D,"<=14")', INT),
          ("STATED VALUE", f"=SUM({T}!K2:K)", ("NUMBER", '$#,##0,,,"B"'))])
section(tab, S, 24, 1, 5, "Open tenders by region"); section(tab, S, 24, 7, 8, "Pursue by region")
put(tab, 25, 1, [[f"=QUERY({T}!A2:AE,\"select H, count(S), sum(K), sum(U) where S is not null group by H order by count(S) desc label H 'Region', count(S) 'Open tenders', sum(K) 'Stated value', sum(U) 'Expected value'\",1)"]])
put(tab, 25, 7, [[f"=QUERY({T}!A2:AE,\"select H, count(S) where T = 'Pursue' group by H order by count(S) desc label H 'Region', count(S) 'Pursue'\",1)"]])
table_header(S, 25, 1, 5); table_header(S, 25, 7, 8); put(tab, 25, 5, [["Share"]])
bars(tab, S, 26, 39, 2, 5); nf(S, 26, 39, 3, 4, USD); rows_style(S, 26, 39, 1, 5); rows_style(S, 26, 39, 7, 8)
section(tab, S, 41, 1, 5, "Open tenders by sector"); section(tab, S, 41, 7, 8, "Pursue by sector")
put(tab, 42, 1, [[f"=QUERY({T}!A2:AE,\"select F, count(S), sum(K), sum(U) where S is not null group by F order by count(S) desc label F 'Sector', count(S) 'Open tenders', sum(K) 'Stated value', sum(U) 'Expected value'\",1)"]])
put(tab, 42, 7, [[f"=QUERY({T}!A2:AE,\"select F, count(S) where T = 'Pursue' group by F order by count(S) desc label F 'Sector', count(S) 'Pursue'\",1)"]])
table_header(S, 42, 1, 5); table_header(S, 42, 7, 8); put(tab, 42, 5, [["Share"]])
bars(tab, S, 43, 68, 2, 5); nf(S, 43, 68, 3, 4, USD); rows_style(S, 43, 68, 1, 5); rows_style(S, 43, 68, 7, 8)
section(tab, S, 70, 1, 5, "Open tenders by source"); section(tab, S, 70, 7, 11, "Closing in the next 14 days - Pursue and Watch")
put(tab, 71, 1, [[f"=QUERY({T}!A2:AE,\"select L, count(S), count(K) where S is not null group by L order by count(S) desc label L 'Source', count(S) 'Open tenders', count(K) 'With stated value'\",1)"]])
table_header(S, 71, 1, 5); put(tab, 71, 5, [["Share"]]); bars(tab, S, 72, 130, 2, 5, "teal"); rows_style(S, 72, 130, 1, 5)
table_header(S, 71, 7, 11, ["Tender", "Country", "", "Decision", "Deadline"], tab)
put(tab, 72, 7, [[f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{T}!J2:J,{T}!G2:G,{T}!AC2:AC,{T}!T2:T,{T}!C2:C}},{T}!D2:D>=0,{T}!D2:D<=14,({T}!T2:T="Pursue")+({T}!T2:T="Watch")),3,FALSE),58,5),"None")']])
nf(S, 72, 130, 11, 11, DATE); decision_chips([rng(S, 72, 130, 10, 10)]); rows_style(S, 72, 130, 7, 11)
chart(S, "Open tenders by region", rng(S, 26, 39, 1, 1), rng(S, 26, 39, 2, 2), 8, 1, 560, 300)
chart(S, "Open tenders by sector (top)", rng(S, 43, 58, 1, 1), rng(S, 43, 58, 2, 2), 8, 5, 560, 300, color="teal")

# ---- Israel Overview
S, tab = 49, "Israel Overview"
analysis(tab, S, 10, [240, 110, 260, 110, 110, 2, 230, 130, 2, 230],
         "Israel", "Tenders and calls for proposals from municipalities, councils, government companies, statutory bodies, water corporations, hospitals and academia. Scanned daily.",
         [("OPEN NOTICES", f"=COUNTA({IL}!O2:O)", INT), ("NEW IN 48H", f'=COUNTIF({IL}!B2:B,"NEW")', INT),
          ("PUBLISHING BODIES", f"=COUNTUNIQUE({IL}!C2:C)", INT), ("CLOSING IN 7 DAYS", f'=COUNTIFS({IL}!J2:J,">=0",{IL}!J2:J,"<=7")', INT),
          ("CALLS FOR PROPOSALS", f'=COUNTIF({IL}!F2:F,"call")', INT)])
section(tab, S, 24, 1, 2, "By type of body"); section(tab, S, 24, 3, 4, "By district"); section(tab, S, 24, 7, 8, "Most active publishers")
put(tab, 25, 1, [[f"=QUERY({IL}!A2:O,\"select D, count(O) where O is not null group by D order by count(O) desc label D 'Type of body', count(O) 'Notices'\",1)"]])
put(tab, 25, 3, [[f"=QUERY({IL}!A2:O,\"select E, count(O) where O is not null and E is not null group by E order by count(O) desc label E 'District', count(O) 'Notices'\",1)"]])
put(tab, 25, 7, [[f"=QUERY({IL}!A2:O,\"select C, count(O) where O is not null group by C order by count(O) desc limit 16 label C 'Body', count(O) 'Notices'\",1)"]])
for c1, c2 in ((1, 2), (3, 4), (7, 8)):
    table_header(S, 25, c1, c2); rows_style(S, 26, 41, c1, c2)
section(tab, S, 44, 1, 10, "Closing in the next 10 days")
table_header(S, 45, 1, 10, ["Body", "Type", "Title (Hebrew)", "Deadline", "Days left", "", "Kind", "Sector", "", "Link"], tab)
put(tab, 46, 1, [[f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{IL}!C2:C,{IL}!D2:D,{IL}!H2:H,{IL}!I2:I,{IL}!J2:J,{IL}!O2:O,{IL}!F2:F,{IL}!L2:L,{IL}!G2:G,{IL}!M2:M}},{IL}!J2:J<>"",{IL}!J2:J>=0,{IL}!J2:J<=10),5,TRUE),25,10),"None")']])
nf(S, 46, 70, 4, 4, DATE); rows_style(S, 46, 70, 1, 10); chip([rng(S, 46, 70, 5, 5)], "4", "red", "red_bg", "NUMBER_LESS")
section(tab, S, 73, 1, 10, "Calls for proposals (קולות קוראים) - newest first")
table_header(S, 74, 1, 10, ["Body", "Type", "Title (Hebrew)", "Deadline", "Days left", "", "First seen", "Sector", "", "Link"], tab)
put(tab, 75, 1, [[f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{IL}!C2:C,{IL}!D2:D,{IL}!H2:H,{IL}!I2:I,{IL}!J2:J,{IL}!O2:O,{IL}!A2:A,{IL}!L2:L,{IL}!G2:G,{IL}!M2:M}},{IL}!F2:F="call"),7,FALSE),30,10),"None")']])
nf(S, 75, 104, 4, 4, DATE); nf(S, 75, 104, 7, 7, DATE); rows_style(S, 75, 104, 1, 10)
fmt(rng(S, 46, 104, 3, 3), {"horizontalAlignment": "RIGHT"}, "userEnteredFormat.horizontalAlignment")
chart(S, "Open notices by type of body", rng(S, 26, 40, 1, 1), rng(S, 26, 40, 2, 2), 8, 1, 520, 300)
chart(S, "Open notices by district", rng(S, 26, 34, 3, 3), rng(S, 26, 34, 4, 4), 8, 4, 520, 300, kind="COLUMN", color="teal")

# ---- USA
S, tab = 57, "USA"
U_OPEN = f'{T}!G2:G="USA",NOT(REGEXMATCH({T}!M2:M&{T}!N2:N,"(?i)set-aside"))'
analysis(tab, S, 11, [70, 430, 260, 200, 110, 100, 70, 60, 90, 160, 230],
         "USA", "US federal (SAM.gov), New York City and the 20 largest US cities. Set-asides for US small businesses are excluded from the lists below.",
         [("US OPEN TENDERS", f'=COUNTIF({T}!G2:G,"USA")', INT),
          ("OPEN TO FOREIGN FIRMS", f'=IFERROR(ROWS(FILTER({T}!G2:G,{U_OPEN})),0)', INT),
          ("SMALL-BUSINESS SET-ASIDES", f'=COUNTIFS({T}!G2:G,"USA",{T}!N2:N,"*set-aside*")', INT),
          ("CITIES AND NYC", f'=COUNTIFS({T}!G2:G,"USA",{T}!L2:L,"US city*")+COUNTIFS({T}!G2:G,"USA",{T}!L2:L,"NYC*")', INT),
          ("CLOSING IN 14 DAYS", f'=COUNTIFS({T}!G2:G,"USA",{T}!D2:D,">=0",{T}!D2:D,"<=14")', INT)], rows=400)
section(tab, S, 24, 1, 3, "Open to foreign firms by sector"); section(tab, S, 24, 5, 7, "By source")
put(tab, 25, 1, [[f"=QUERY({T}!A2:AE,\"select F, count(S) where G = 'USA' and not M contains 'set-aside' group by F order by count(S) desc label F 'Sector', count(S) 'Tenders'\",1)"]])
put(tab, 25, 5, [[f"=QUERY({T}!A2:AE,\"select L, count(S) where G = 'USA' group by L order by count(S) desc label L 'Source', count(S) 'Tenders'\",1)"]])
table_header(S, 25, 1, 3); put(tab, 25, 3, [["Share"]]); bars(tab, S, 26, 49, 2, 3)
table_header(S, 25, 5, 6); rows_style(S, 26, 49, 1, 3); rows_style(S, 26, 40, 5, 6)
section(tab, S, 52, 1, 11, "Best US tenders for Sinder - open to foreign firms, best fit first")
table_header(S, 53, 1, 11, ["Fit", "Tender", "Buyer", "Sector", "Value (USD)", "Deadline", "Days left", "", "Decision", "Notice type", "Link"], tab)
put(tab, 54, 1, [[f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{T}!AC2:AC,{T}!J2:J,{T}!I2:I,{T}!F2:F,{T}!K2:K,{T}!C2:C,{T}!D2:D,{T}!S2:S,{T}!T2:T,{T}!N2:N,{T}!P2:P}},{U_OPEN},N({T}!D2:D)>=3),1,FALSE,7,TRUE),300,11),"Waiting for the next refresh")']])
nf(S, 54, 353, 5, 5, USD); nf(S, 54, 353, 6, 6, DATE); rows_style(S, 54, 353, 1, 11)
decision_chips([rng(S, 54, 353, 9, 9)]); chip([rng(S, 54, 353, 7, 7)], "7", "red", "red_bg", "NUMBER_LESS")
req.append({"addConditionalFormatRule": {"rule": {"ranges": [rng(S, 54, 353, 1, 1)], "gradientRule": {
    "minpoint": {"colorStyle": {"rgbColor": rgb(C["white"])}, "type": "NUMBER", "value": "40"},
    "maxpoint": {"colorStyle": {"rgbColor": rgb("8FD3B0")}, "type": "NUMBER", "value": "100"}}}, "index": 0}})
chart(S, "US tenders open to foreign firms, by sector", rng(S, 26, 40, 1, 1), rng(S, 26, 40, 2, 2), 8, 1, 1100, 300)

# ---- Deals
S, tab = 50, "Deals"
analysis(tab, S, 10, [80, 380, 170, 130, 100, 100, 130, 130, 110, 430],
         "Deals", "What the deal calculation says: expected value = win probability x deal value x net margin - pursuit cost, weighted by Profile and Partners.",
         [("PURSUE DEALS", f'=COUNTIF({DC}!B2:B,"Pursue")', INT), ("EXPECTED VALUE", f'=SUMIF({DC}!B2:B,"Pursue",{DC}!C2:C)', USD),
          ("PRIORITY VALUE", f'=SUMIF({DC}!B2:B,"Pursue",{DC}!AE2:AE)', USD),
          ("MEDIAN NET MARGIN", f'=IFERROR(MEDIAN(FILTER({DC}!L2:L,{DC}!B2:B="Pursue")),"")', PCT1),
          ("SUB-SUPPLY TO WATCH", f'=COUNTIFS({DC}!B2:B,"Watch",{DC}!AC2:AC,"sub-supply to the winner")', INT)])
section(tab, S, 24, 1, 4, "Pursue deals by route"); section(tab, S, 24, 6, 9, "Pursue deals by region")
put(tab, 25, 1, [[f"=QUERY({DC}!A2:AE,\"select AC, count(A), sum(C), avg(E) where B = 'Pursue' group by AC order by sum(C) desc label AC 'Route', count(A) 'Deals', sum(C) 'Expected value', avg(E) 'Avg win prob.'\",1)"]])
put(tab, 25, 6, [[f"=QUERY({DC}!A2:AE,\"select AB, count(A), sum(C), avg(L) where B = 'Pursue' group by AB order by sum(C) desc label AB 'Region', count(A) 'Deals', sum(C) 'Expected value', avg(L) 'Avg net margin'\",1)"]])
table_header(S, 25, 1, 4); table_header(S, 25, 6, 9)
nf(S, 26, 32, 3, 3, USD); nf(S, 26, 32, 4, 4, PCT); nf(S, 26, 39, 8, 8, USD); nf(S, 26, 39, 9, 9, PCT1)
rows_style(S, 26, 32, 1, 4); rows_style(S, 26, 39, 6, 9)
section(tab, S, 41, 1, 6, "Pursue deals by sector")
put(tab, 42, 1, [[f"=QUERY({DC}!A2:AE,\"select T, count(A), sum(C), avg(L), avg(E) where B = 'Pursue' group by T order by sum(C) desc label T 'Sector', count(A) 'Deals', sum(C) 'Expected value', avg(L) 'Avg net margin', avg(E) 'Avg win prob.'\",1)"]])
table_header(S, 42, 1, 6); put(tab, 42, 6, [["Share of value"]]); bars(tab, S, 43, 68, 3, 6, "green")
nf(S, 43, 68, 3, 3, USD); nf(S, 43, 68, 4, 4, PCT1); nf(S, 43, 68, 5, 5, PCT); rows_style(S, 43, 68, 1, 6)
section(tab, S, 70, 1, 10, "Top 30 deals by priority value")
table_header(S, 71, 1, 10, ["Country", "Opportunity", "Route", "Deal value", "Net margin", "Win prob.", "Expected value", "Priority value", "Deadline", "Why"], tab)
put(tab, 72, 1, [[f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{DC}!S2:S,{DC}!W2:W,{DC}!AC2:AC,{DC}!F2:F,{DC}!L2:L,{DC}!E2:E,{DC}!C2:C,{DC}!AE2:AE,{DC}!X2:X,{DC}!Z2:Z}},{DC}!B2:B="Pursue"),8,FALSE),30,10),"Waiting for the next refresh")']])
nf(S, 72, 101, 4, 4, USD); nf(S, 72, 101, 5, 5, PCT1); nf(S, 72, 101, 6, 6, PCT); nf(S, 72, 101, 7, 8, USD); nf(S, 72, 101, 9, 9, DATE)
rows_style(S, 72, 101, 1, 10); fmt(rng(S, 72, 101, 8, 8), {"textFormat": text("green", 10, True)}, "userEnteredFormat.textFormat")
section(tab, S, 104, 1, 10, "Buyers in the news - world press on the buyers of the best deals (GDELT)")
table_header(S, 105, 1, 5, ["Date", "Headline", "Buyer", "Source", "Link"], tab)
put(tab, 106, 1, [["=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({Press!D2:D,Press!E2:E,Press!B2:B,Press!F2:F,Press!G2:G},Press!G2:G<>\"\"),1,FALSE),20,5),\"No linked articles yet - the press check runs with the next data refresh\")"]])
rows_style(S, 106, 125, 1, 5)
chart(S, "Expected value by region (Pursue)", rng(S, 26, 35, 6, 6), rng(S, 26, 35, 8, 8), 8, 1, 560, 300, color="green")
chart(S, "Expected value by sector (Pursue)", rng(S, 43, 54, 1, 1), rng(S, 43, 54, 3, 3), 8, 4, 560, 300)

# ---- Commodities
S, tab = 51, "Commodities"
analysis(tab, S, 9, [300, 130, 120, 120, 120, 120, 120, 200, 200],
         "Commodities", "World Bank monthly prices per commodity group (a factor in the deal calculation) and the live prices of the Commodities Tracker.",
         [("GROUPS RISING", f'=COUNTIF({PT}!B2:B,"rising*")', INT), ("GROUPS FALLING", f'=COUNTIF({PT}!B2:B,"falling*")', INT),
          ("TRACKED PRICES", f"=COUNTA({CP}!A2:A)", INT), ("LATEST PRICE DATE", f"=MAX({CP}!G2:G)", DATE)])
section(tab, S, 24, 1, 6, "Price signals by commodity group")
table_header(S, 25, 1, 6, ["Commodity group", "Signal", "1 month", "3 months", "12 months", "World Bank series"], tab)
put(tab, 26, 1, [[f'=IFERROR(SORT(FILTER({{{PT}!A2:A,{PT}!B2:B,{PT}!C2:C,{PT}!D2:D,{PT}!E2:E,{PT}!F2:F}},{PT}!A2:A<>""),ABS(FILTER({PT}!D2:D,{PT}!A2:A<>"")),FALSE),"Waiting for the next refresh")']])
nf(S, 26, 43, 3, 5, PCTV); rows_style(S, 26, 43, 1, 6)
for v, fg, bg in (("rising fast", "red", "red_bg"), ("rising", "amber", "amber_bg"), ("falling fast", "green", "green_bg"), ("falling", "green", "green_bg"), ("stable", "muted", "gray_bg")):
    chip([rng(S, 26, 43, 2, 2)], v, fg, bg)
section(tab, S, 45, 1, 7, "Biggest 3-month moves - World Bank series")
table_header(S, 46, 1, 7, ["Series", "Group", "Unit", "Price", "1 month", "3 months", "12 months"], tab)
put(tab, 47, 1, [[f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{PS}!B2:B,{PS}!A2:A,{PS}!C2:C,{PS}!E2:E,{PS}!F2:F,{PS}!G2:G,{PS}!H2:H}},{PS}!B2:B<>""),ABS(FILTER({PS}!G2:G,{PS}!B2:B<>"")),FALSE),20,7),"Waiting for the next refresh")']])
nf(S, 47, 66, 4, 4, ("NUMBER", "#,##0.00")); nf(S, 47, 66, 5, 7, PCTV); rows_style(S, 47, 66, 1, 7)
section(tab, S, 68, 1, 6, "Benchmark prices - exchanges and official sources (Commodities Tracker)")
put(tab, 69, 1, [[f"=IFERROR(QUERY({CP}!A2:J,\"select C, D, E, G, H, I where I starts with 'T1' or I starts with 'T2' limit 60 label C 'Commodity', D 'Price (USD)', E 'Unit', G 'Date', H 'Source', I 'Quality'\",1),\"Waiting for the next refresh\")"]])
table_header(S, 69, 1, 6); nf(S, 70, 130, 2, 2, ("NUMBER", "#,##0.00")); nf(S, 70, 130, 4, 4, DATE); rows_style(S, 70, 130, 1, 6)
for rr in ((26, 43), (47, 66)):
    req.append({"addConditionalFormatRule": {"rule": {"ranges": [rng(S, rr[0], rr[1], 3, 7)], "booleanRule": {
        "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0"}]}, "format": {"textFormat": {"foregroundColorStyle": {"rgbColor": rgb(C["red"])}}}}}, "index": 0}})
    req.append({"addConditionalFormatRule": {"rule": {"ranges": [rng(S, rr[0], rr[1], 3, 7)], "booleanRule": {
        "condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]}, "format": {"textFormat": {"foregroundColorStyle": {"rgbColor": rgb(C["green"])}}}}}, "index": 0}})
chart(S, "3-month price change by commodity group (%)", rng(S, 26, 43, 1, 1), rng(S, 26, 43, 4, 4), 8, 1, 1100, 300)

# ---- Buyers
S, tab = 52, "Buyers"
analysis(tab, S, 7, [400, 90, 240, 120, 140, 320, 260],
         "Buyers", "Who buys, how often and when next: award history from every award source. Refreshed every 4 hours.",
         [("REPEAT BUYERS", f"=COUNTA({RB}!A2:A)", INT),
          ("EXPECTED IN 60 DAYS", f'=COUNTIFS({RB}!H2:H,">="&TODAY(),{RB}!H2:H,"<="&(TODAY()+60))', INT),
          ("AWARDS TRACKED", "=COUNTA(Awards!A2:A)", INT)])
section(tab, S, 8, 1, 7, "Expected to buy in the next 60 days")
table_header(S, 9, 1, 7, ["Buyer", "Country", "Commodity group", "Awards (12m)", "Next expected", "Current suppliers", "Buyer email"], tab)
put(tab, 10, 1, [[f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{RB}!A2:A,{RB}!B2:B,{RB}!C2:C,{RB}!D2:D,{RB}!H2:H,{RB}!I2:I,{RB}!K2:K}},{RB}!H2:H>=TODAY(),{RB}!H2:H<=TODAY()+60),5,TRUE),25,7),"None")']])
nf(S, 10, 34, 5, 5, DATE); rows_style(S, 10, 34, 1, 7)
section(tab, S, 37, 1, 7, "Most active buyers (awards in the last 12 months)")
put(tab, 38, 1, [[f"=IFERROR(QUERY({RB}!A2:O,\"select A, B, C, D, E, M where A is not null order by D desc limit 30 label A 'Buyer', B 'Country', C 'Commodity group', D 'Awards (12m)', E 'Total awarded', M 'Median award'\",1),\"\")"]])
table_header(S, 38, 1, 6); nf(S, 39, 68, 5, 6, USD); rows_style(S, 39, 68, 1, 6)
put(tab, 38, 7, [["Activity"]]); table_header(S, 38, 7, 7); bars(tab, S, 39, 68, 4, 7)

# ================================================================== work tables and raw data
def table_tab(sid, ncols, ws, raw=False, header_rows=1, protect=False, freeze_cols=1):
    reset.append(sid)
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "rightToLeft": False, "gridProperties": {
        "frozenRowCount": header_rows, "frozenColumnCount": freeze_cols, "hideGridlines": False}},
        "fields": "rightToLeft,gridProperties(frozenRowCount,frozenColumnCount,hideGridlines)"}})
    fmt({"sheetId": sid, "startRowIndex": header_rows, "startColumnIndex": 0, "endColumnIndex": ncols},
        {"wrapStrategy": "CLIP", "verticalAlignment": "MIDDLE", "textFormat": text("text", 10)},
        "userEnteredFormat(wrapStrategy,verticalAlignment,textFormat)")
    fmt(rng(sid, 1, header_rows, 1, ncols), {"backgroundColorStyle": {"rgbColor": rgb(C["blue"] if raw else C["navy"])},
                                             "textFormat": text("white", 9, True), "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"},
        "userEnteredFormat(backgroundColorStyle,textFormat,wrapStrategy,verticalAlignment)")
    heights(sid, 1, header_rows, 40)
    if ws:
        widths(sid, ws)
    req.append({"addBanding": {"bandedRange": {"range": {"sheetId": sid, "startRowIndex": header_rows, "startColumnIndex": 0, "endColumnIndex": ncols},
                                               "rowProperties": {"firstBandColorStyle": {"rgbColor": rgb(C["white"])},
                                                                 "secondBandColorStyle": {"rgbColor": rgb(C["card"])}}}}})
    req.append({"setBasicFilter": {"filter": {"range": {"sheetId": sid, "startRowIndex": 0, "startColumnIndex": 0, "endColumnIndex": ncols}}}})
    if protect:
        req.append({"addProtectedRange": {"protectedRange": {"range": {"sheetId": sid}, "warningOnly": True,
                                                             "description": "Filled automatically by the pipeline - edits are overwritten"}}})


TEN = 1
table_tab(TEN, 31, [60, 50, 95, 60, 70, 190, 60, 130, 230, 420, 120, 150, 140, 120, 180, 220, 150, 200, 160, 80, 110, 70, 70, 70, 70, 110, 200, 380, 60, 70, 70],
          raw=True, protect=True, freeze_cols=0)
nf(TEN, 2, 0, 3, 3, DATE); nf(TEN, 2, 0, 11, 11, USD); nf(TEN, 2, 0, 21, 21, USD); nf(TEN, 2, 0, 22, 22, PCT)
nf(TEN, 2, 0, 24, 24, PCT); nf(TEN, 2, 0, 26, 26, USD)
decision_chips([rng(TEN, 2, 0, 20, 20)]); chip([rng(TEN, 2, 0, 2, 2)], "NEW", "green", "green_bg")
chip([rng(TEN, 2, 0, 4, 4)], "7", "red", "red_bg", "NUMBER_LESS")
req.append({"addConditionalFormatRule": {"rule": {"ranges": [rng(TEN, 2, 0, 29, 29)], "gradientRule": {
    "minpoint": {"colorStyle": {"rgbColor": rgb(C["white"])}, "type": "NUMBER", "value": "40"},
    "maxpoint": {"colorStyle": {"rgbColor": rgb("8FD3B0")}, "type": "NUMBER", "value": "100"}}}, "index": 0}})
table_tab(41, 15, [90, 55, 230, 140, 90, 80, 90, 480, 95, 70, 95, 160, 250, 200, 120], raw=True, protect=True)
nf(41, 2, 0, 1, 1, DATE); nf(41, 2, 0, 9, 9, DATE); nf(41, 2, 0, 11, 11, DATE); chip([rng(41, 2, 0, 2, 2)], "NEW", "green", "green_bg")
chip([rng(41, 2, 0, 6, 6)], "call", "accent", "light"); chip([rng(41, 2, 0, 6, 6)], "exemption", "muted", "gray_bg")
table_tab(40, 37, [150, 80, 110, 60, 70, 120, 140, 70, 70, 70, 70, 70, 110, 90, 70, 70, 70, 90, 60, 190, 160, 220, 380, 95, 200, 420, 60, 130, 150, 60, 110, 70, 70, 380, 60, 320, 160],
          raw=True, protect=True)
nf(40, 2, 0, 3, 3, USD); nf(40, 2, 0, 4, 4, ("NUMBER", '0.0"x"')); nf(40, 2, 0, 5, 5, PCT); nf(40, 2, 0, 6, 6, USD)
nf(40, 2, 0, 8, 10, PCT); nf(40, 2, 0, 11, 12, PCT1); nf(40, 2, 0, 13, 14, USD); nf(40, 2, 0, 24, 24, DATE)
nf(40, 2, 0, 31, 31, USD); decision_chips([rng(40, 2, 0, 2, 2)])
for sid, n, ws in ((8, 15, [360, 70, 200, 80, 130, 160, 100, 100, 320, 70, 230, 220, 120, 80, 260]),
                   (9, 26, None), (43, 10, [90, 70, 380, 100, 110, 220, 100, 230, 170, 260])):
    table_tab(sid, n, ws, raw=True, protect=True)
table_tab("@sheet:Upcoming", 28, None, raw=True, protect=True)
table_tab("@sheet:Press", 7, [150, 300, 70, 90, 420, 180, 260], raw=True, protect=True)
# work tables (agents append rows; no protection)
for sid, n, ws in ((47, 18, [150, 320, 220, 70, 150, 150, 120, 90, 120, 90, 120, 90, 280, 110, 110, 220, 200, 110]),
                   (24, 22, [170, 90, 80, 320, 240, 70, 170, 110, 120, 220, 320, 320, 260, 320, 320, 280, 110, 320, 260, 90, 200, 260]),
                   (28, 18, None), (26, 12, [110, 120, 120, 160, 260, 200, 260, 80, 480, 220, 120, 160]),
                   (29, 16, [150, 90, 120, 140, 110, 160, 380, 380, 420, 420, 70, 95, 200, 100, 220, 95]),
                   (13, 13, [90, 70, 120, 170, 380, 420, 260, 110, 260, 320, 260, 70, 220]),
                   (18, 19, None), (46, 7, [90, 140, 420, 220, 300, 240, 100])):
    table_tab(sid, n, ws)
for sid in (29, 13):
    chip([rng(sid, 2, 0, 11 if sid == 29 else 2, 11 if sid == 29 else 2)], "High", "amber", "amber_bg")
chip([rng(24, 2, 0, 17, 17)], "Go", "green", "green_bg"); chip([rng(24, 2, 0, 17, 17)], "No-go", "muted", "gray_bg")
chip([rng(24, 2, 0, 17, 17)], "Need info", "amber", "amber_bg")
chip([rng(26, 2, 0, 8, 8)], "done", "green", "green_bg"); chip([rng(26, 2, 0, 8, 8)], "queued", "amber", "amber_bg")
chip([rng(26, 2, 0, 8, 8)], "running", "accent", "light"); chip([rng(26, 2, 0, 8, 8)], "error", "red", "red_bg")
# pipeline rules again (reset removed them)
req.append({"addConditionalFormatRule": {"rule": {"ranges": [rng(47, 2, 0, 14, 14)], "booleanRule": {"condition": {"type": "CUSTOM_FORMULA",
    "values": [{"userEnteredValue": '=AND($N2<>"",$N2<TODAY(),NOT(REGEXMATCH($F2,"Won|Lost|Dropped")))'}]},
    "format": {"backgroundColorStyle": {"rgbColor": rgb(C["red_bg"])}, "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": rgb(C["red"])}}}}}, "index": 0}})
chip([rng(47, 2, 0, 6, 6)], "Won", "green", "green_bg"); chip([rng(47, 2, 0, 6, 6)], "Lost", "muted", "gray_bg")

# ================================================================== zone dividers and tab order
for sid, name, line in ((53, "ANALYSIS", "Analysis  -  one screen per kind of data: markets, Israel, deals, commodities, buyers, intelligence"),
                        (54, "RAW DATA", "Raw data  -  filled automatically by the pipeline. Filter and read freely; edits are overwritten."),
                        (55, "SETTINGS", "Settings  -  your weights, partners, assumptions, the research worker's queue and the guide")):
    reset.append(sid)
    clear.append(f"'{name}'!A1:D6")
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"hideGridlines": True, "rowCount": 6, "columnCount": 4}},
                                          "fields": "gridProperties(hideGridlines,rowCount,columnCount)"}})
    put(name, 1, 1, [[line]])
    fmt(rng(sid, 1, 6, 1, 4), {"backgroundColorStyle": {"rgbColor": rgb(C["navy"])}}, "userEnteredFormat.backgroundColorStyle")
    fmt(rng(sid, 1, 1, 1, 1), {"textFormat": text("white", 14, True), "padding": {"left": 16}, "wrapStrategy": "OVERFLOW_CELL"},
        "userEnteredFormat(textFormat,padding,wrapStrategy)")
    heights(sid, 1, 1, 64); widths(sid, [1000, 60, 60, 60])
NAVY, TEAL, GRAYT, AMBER, BLACK = C["navy"], C["teal"], C["gray_tab"], C["amber_tab"], C["black"]
ORDER = [(45, NAVY), (31, NAVY), (47, NAVY), (24, NAVY),
         (53, BLACK), (50, TEAL), (48, TEAL), (49, TEAL), (57, TEAL), (51, TEAL), (52, TEAL), (29, TEAL), (13, TEAL),
         (54, BLACK), (1, GRAYT), (41, GRAYT), (40, GRAYT), ("@sheet:Press", GRAYT),
         (55, BLACK), (19, AMBER), (46, AMBER), (15, AMBER), (26, AMBER), (25, AMBER)]
# kept (formulas and agents use them) but hidden: their content is shown on the analysis screens
HIDE = [28, 18, "@sheet:Upcoming", 8, 9, 43, 42, 44, 23, 20, 21, 10, 12, 11, 14, 2, 3, 5, 864500415,
        1203289973, 1755813676, 4]
for i, (sid, color) in enumerate(ORDER):
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "index": i, "hidden": False, "tabColorStyle": {"rgbColor": rgb(color)}},
                                          "fields": "index,hidden,tabColorStyle"}})

for i, sid in enumerate(HIDE):
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "index": len(ORDER) + i, "hidden": True},
                                          "fields": "index,hidden"}})
pre = [{"addSheet": {"properties": {"sheetId": LISTS, "title": "Lists", "hidden": True, "gridProperties": {"rowCount": 100, "columnCount": 26}}}},
       {"addSheet": {"properties": {"sheetId": 57, "title": "USA", "gridProperties": {"rowCount": 400, "columnCount": 12}}}}]
out = {"reset": reset, "pre_requests": pre, "clear": clear, "values": values, "requests": req}
Path(__file__).with_name("design.json").write_text(json.dumps(out, ensure_ascii=False))
print(len(values), "value ranges,", len(req), "requests,", len(reset), "tabs reset")
