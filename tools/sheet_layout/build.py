"""Builds the Leads Engine layout (English, LTR): work / analysis / raw data / settings zones, the analysis tabs and
the Assumptions tab. Output: tools/sheet_layout/layout.json, applied with
  python -m leads.push layout <spreadsheet id> tools/sheet_layout/layout.json
Run with --create the first time (adds the new tabs)."""
import json
import sys
from pathlib import Path

NAVY, BLUE, LIGHT, KPI_BG, TEXT, MUTED = "0F1F3A", "1F3B63", "DCE4EE", "EEF2F7", "1F2A37", "5F6B7A"
TEAL, GRAY, AMBER, BLACK = "0E7C86", "8A94A6", "C27C0E", "000000"
values, req, pre = [], [], []


def rgb(h):
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def rng(sid, r1, r2, c1, c2):
    return {"sheetId": sid, "startRowIndex": r1 - 1, "endRowIndex": r2, "startColumnIndex": c1 - 1, "endColumnIndex": c2}


def fmt(r, f, fields):
    req.append({"repeatCell": {"range": r, "cell": {"userEnteredFormat": f}, "fields": fields}})


def put(tab, cell, rows):
    values.append({"range": f"'{tab}'!{cell}", "rows": rows})


def widths(sid, ws):
    for i, w in enumerate(ws):
        req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                                  "properties": {"pixelSize": w}, "fields": "pixelSize"}})


def height(sid, r, h):
    req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": r - 1, "endIndex": r},
                                              "properties": {"pixelSize": h}, "fields": "pixelSize"}})


def base(sid, rows, cols):
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "rightToLeft": False,
                                                         "gridProperties": {"hideGridlines": True, "rowCount": rows, "columnCount": cols}},
                                          "fields": "rightToLeft,gridProperties.hideGridlines,gridProperties.rowCount,gridProperties.columnCount"}})
    req.append({"unmergeCells": {"range": rng(sid, 1, rows, 1, cols)}})
    fmt(rng(sid, 1, rows, 1, cols), {"wrapStrategy": "CLIP", "verticalAlignment": "MIDDLE", "backgroundColorStyle": {"rgbColor": rgb("FFFFFF")},
                                     "textFormat": {"fontFamily": "Arial", "fontSize": 10, "bold": False,
                                                    "foregroundColorStyle": {"rgbColor": rgb(TEXT)}}},
        "userEnteredFormat(wrapStrategy,verticalAlignment,backgroundColorStyle,textFormat)")


def title(tab, sid, cols, text, sub):
    put(tab, "A1", [[text]]); put(tab, "A2", [[sub]])
    for r, size, color, italic, h in ((1, 18, "FFFFFF", False, 46), (2, 10, "B8C4D6", True, 24)):
        req.append({"mergeCells": {"range": rng(sid, r, r, 1, cols), "mergeType": "MERGE_ALL"}})
        fmt(rng(sid, r, r, 1, cols), {"backgroundColorStyle": {"rgbColor": rgb(NAVY)}, "padding": {"left": 12},
                                      "textFormat": {"bold": r == 1, "italic": italic, "fontSize": size, "foregroundColorStyle": {"rgbColor": rgb(color)}}},
            "userEnteredFormat(backgroundColorStyle,padding,textFormat)")
        height(sid, r, h)


def kpis(tab, sid, row, items):
    """items: (label, formula, number pattern); each card spans 2 columns."""
    for i, (label, formula, pat) in enumerate(items):
        c = 1 + 2 * i
        col = chr(64 + c)
        put(tab, f"{col}{row}", [[label]]); put(tab, f"{col}{row + 1}", [[formula]])
        for r in (row, row + 1):
            req.append({"mergeCells": {"range": rng(sid, r, r, c, c + 1), "mergeType": "MERGE_ALL"}})
        fmt(rng(sid, row + 1, row + 1, c, c + 1), {"numberFormat": {"type": "NUMBER", "pattern": pat}}, "userEnteredFormat.numberFormat")
    n = 2 * len(items)
    fmt(rng(sid, row, row, 1, n), {"backgroundColorStyle": {"rgbColor": rgb(KPI_BG)}, "horizontalAlignment": "CENTER",
                                   "textFormat": {"bold": True, "fontSize": 9, "foregroundColorStyle": {"rgbColor": rgb(MUTED)}}},
        "userEnteredFormat(backgroundColorStyle,horizontalAlignment,textFormat)")
    fmt(rng(sid, row + 1, row + 1, 1, n), {"backgroundColorStyle": {"rgbColor": rgb(KPI_BG)}, "horizontalAlignment": "CENTER",
                                           "textFormat": {"bold": True, "fontSize": 20, "foregroundColorStyle": {"rgbColor": rgb(NAVY)}}},
        "userEnteredFormat(backgroundColorStyle,horizontalAlignment,textFormat)")
    height(sid, row + 1, 44)
    for i in range(1, len(items)):
        req.append({"updateBorders": {"range": rng(sid, row, row + 1, 2 * i, 2 * i), "right": {"style": "SOLID_THICK", "colorStyle": {"rgbColor": rgb("FFFFFF")}}}})


def section(tab, sid, row, c1, c2, text):
    put(tab, f"{chr(64 + c1)}{row}", [[text]])
    req.append({"mergeCells": {"range": rng(sid, row, row, c1, c2), "mergeType": "MERGE_ALL"}})
    fmt(rng(sid, row, row, c1, c2), {"backgroundColorStyle": {"rgbColor": rgb(BLUE)}, "padding": {"left": 10},
                                     "textFormat": {"bold": True, "fontSize": 11, "foregroundColorStyle": {"rgbColor": rgb("FFFFFF")}}},
        "userEnteredFormat(backgroundColorStyle,padding,textFormat)")
    height(sid, row, 28)


def header(sid, row, c1, c2):
    fmt(rng(sid, row, row, c1, c2), {"backgroundColorStyle": {"rgbColor": rgb(LIGHT)},
                                     "textFormat": {"bold": True, "fontSize": 9, "foregroundColorStyle": {"rgbColor": rgb(TEXT)}}},
        "userEnteredFormat(backgroundColorStyle,textFormat)")


def numfmt(sid, r1, r2, c1, c2, pat, typ="NUMBER"):
    fmt(rng(sid, r1, r2, c1, c2), {"numberFormat": {"type": typ, "pattern": pat}}, "userEnteredFormat.numberFormat")


USD, PCT, PCT1, INT, DATE = "$#,##0", "0%", "0.0%", "#,##0", "dd mmm yyyy"
DC, T, IL, PT, PS, CP, RB = "'Deal Calc'", "Tenders", "Israel", "'Price Trends'", "'Price Series'", "'Commodity Prices'", "'Repeat Buyers'"

# ------------------------------------------------------------------ Markets
S = 48; tab = "Markets"
base(S, 130, 11); widths(S, [230, 110, 140, 140, 30, 230, 90, 30, 110, 110, 110])
title(tab, S, 11, "Markets - where the open tenders are", "Every open notice from all sources, by region, sector and source. Refreshed every 4 hours from the Tenders tab.")
kpis(tab, S, 4, [("Open tenders", f"=COUNTA({T}!S2:S)", INT), ("Pursue", f'=COUNTIF({T}!T2:T,"Pursue")', INT),
                 ("Countries", f"=COUNTUNIQUE({T}!G2:G)", INT), ("Closing in 14 days", f'=COUNTIFS({T}!D2:D,">=0",{T}!D2:D,"<=14")', INT),
                 ("Stated value (USD)", f"=SUM({T}!K2:K)", "$#,##0,,\"M\"")])
section(tab, S, 7, 1, 4, "By region"); section(tab, S, 7, 6, 7, "Pursue by region")
put(tab, "A8", [[f"=QUERY({T}!A2:AE,\"select H, count(S), sum(K), sum(U) where S is not null group by H order by count(S) desc label H 'Region', count(S) 'Open tenders', sum(K) 'Stated value (USD)', sum(U) 'Expected value (USD)'\",0)"]])
put(tab, "F8", [[f"=QUERY({T}!A2:AE,\"select H, count(S) where T = 'Pursue' group by H order by count(S) desc label H 'Region', count(S) 'Pursue'\",0)"]])
header(S, 8, 1, 4); header(S, 8, 6, 7); numfmt(S, 9, 22, 3, 4, USD, "CURRENCY")
section(tab, S, 24, 1, 4, "By sector"); section(tab, S, 24, 6, 7, "Pursue by sector")
put(tab, "A25", [[f"=QUERY({T}!A2:AE,\"select F, count(S), sum(K), sum(U) where S is not null group by F order by count(S) desc label F 'Sector', count(S) 'Open tenders', sum(K) 'Stated value (USD)', sum(U) 'Expected value (USD)'\",0)"]])
put(tab, "F25", [[f"=QUERY({T}!A2:AE,\"select F, count(S) where T = 'Pursue' group by F order by count(S) desc label F 'Sector', count(S) 'Pursue'\",0)"]])
header(S, 25, 1, 4); header(S, 25, 6, 7); numfmt(S, 26, 52, 3, 4, USD, "CURRENCY")
section(tab, S, 54, 1, 4, "By source"); section(tab, S, 54, 6, 11, "Closing in the next 14 days - Pursue and Watch, best fit first")
put(tab, "A55", [[f"=QUERY({T}!A2:AE,\"select L, count(S), count(K) where S is not null group by L order by count(S) desc label L 'Source', count(S) 'Open tenders', count(K) 'With stated value'\",0)"]])
put(tab, "F55", [["Tender", "Country", "", "Decision", "Deadline", "Link"]])
put(tab, "F56", [[f"=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{T}!J2:J,{T}!G2:G,{T}!AC2:AC,{T}!T2:T,{T}!C2:C,{T}!P2:P}},{T}!D2:D>=0,{T}!D2:D<=14,({T}!T2:T=\"Pursue\")+({T}!T2:T=\"Watch\")),3,FALSE),60,6),\"None\")"]])
header(S, 55, 1, 3); header(S, 55, 6, 11); numfmt(S, 56, 130, 10, 10, DATE, "DATE")
req.append({"updateDimensionProperties": {"range": {"sheetId": S, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 8},
                                          "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}})

# ------------------------------------------------------------------ Israel Overview
S = 49; tab = "Israel Overview"
base(S, 120, 10); widths(S, [230, 110, 230, 110, 110, 30, 200, 110, 110, 220])
title(tab, S, 10, "Israel - tenders and calls for proposals from ~1,000 public bodies",
      "Municipalities, regional and local councils, government companies, statutory bodies, water corporations, hospitals, academia. Scanned daily.")
kpis(tab, S, 4, [("Open notices", f"=COUNTA({IL}!O2:O)", INT), ("New in 48h", f'=COUNTIF({IL}!B2:B,"NEW")', INT),
                 ("Publishing bodies", f"=COUNTUNIQUE({IL}!C2:C)", INT), ("Closing in 7 days", f'=COUNTIFS({IL}!J2:J,">=0",{IL}!J2:J,"<=7")', INT),
                 ("Calls for proposals", f'=COUNTIF({IL}!F2:F,"call")', INT)])
section(tab, S, 7, 1, 2, "By type of body"); section(tab, S, 7, 3, 4, "By district")
put(tab, "A8", [[f"=QUERY({IL}!A2:O,\"select D, count(O) where O is not null group by D order by count(O) desc label D 'Type of body', count(O) 'Open notices'\",0)"]])
put(tab, "C8", [[f"=QUERY({IL}!A2:O,\"select E, count(O) where O is not null and E is not null group by E order by count(O) desc label E 'District', count(O) 'Open notices'\",0)"]])
header(S, 8, 1, 4)
section(tab, S, 7, 7, 9, "Most active publishers")
put(tab, "G8", [[f"=QUERY({IL}!A2:O,\"select C, D, count(O) where O is not null group by C, D order by count(O) desc limit 20 label C 'Body', D 'Type', count(O) 'Notices'\",0)"]])
header(S, 8, 7, 9)
section(tab, S, 31, 1, 10, "Closing in the next 10 days")
put(tab, "A32", [["Body", "Type", "Title (Hebrew)", "Deadline", "Days left", "", "Kind", "Sector", "", "Link"]])
put(tab, "A33", [[f"=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{IL}!C2:C,{IL}!D2:D,{IL}!H2:H,{IL}!I2:I,{IL}!J2:J,{IL}!O2:O,{IL}!F2:F,{IL}!L2:L,{IL}!G2:G,{IL}!M2:M}},{IL}!J2:J<>\"\",{IL}!J2:J>=0,{IL}!J2:J<=10),5,TRUE),25,10),\"None\")"]])
header(S, 32, 1, 10); numfmt(S, 33, 58, 4, 4, DATE, "DATE")
section(tab, S, 60, 1, 10, "Calls for proposals (קולות קוראים), newest first")
put(tab, "A61", [["Body", "Type", "Title (Hebrew)", "Deadline", "Days left", "", "First seen", "Sector", "", "Link"]])
put(tab, "A62", [[f"=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{IL}!C2:C,{IL}!D2:D,{IL}!H2:H,{IL}!I2:I,{IL}!J2:J,{IL}!O2:O,{IL}!A2:A,{IL}!L2:L,{IL}!G2:G,{IL}!M2:M}},{IL}!F2:F=\"call\"),7,FALSE),30,10),\"None\")"]])
header(S, 61, 1, 10); numfmt(S, 62, 92, 4, 4, DATE, "DATE"); numfmt(S, 62, 92, 7, 7, DATE, "DATE")
for c in (6, 9):
    req.append({"updateDimensionProperties": {"range": {"sheetId": S, "dimension": "COLUMNS", "startIndex": c - 1, "endIndex": c},
                                              "properties": {"pixelSize": 4}, "fields": "pixelSize"}})

# ------------------------------------------------------------------ Deals
S = 50; tab = "Deals"
base(S, 110, 10); widths(S, [80, 380, 160, 120, 90, 90, 120, 120, 100, 420])
title(tab, S, 10, "Deals - what the deal calculation says",
      "Expected value = win probability x deal value x net margin - pursuit cost, weighted by your Profile and Partners. Full detail in the Deal Calc tab.")
kpis(tab, S, 4, [("Pursue deals", f'=COUNTIF({DC}!B2:B,"Pursue")', INT),
                 ("Expected value (USD)", f'=SUMIF({DC}!B2:B,"Pursue",{DC}!C2:C)', "$#,##0"),
                 ("Priority value (USD)", f'=SUMIF({DC}!B2:B,"Pursue",{DC}!AE2:AE)', "$#,##0"),
                 ("Median net margin", f'=IFERROR(MEDIAN(FILTER({DC}!L2:L,{DC}!B2:B="Pursue")),"")', PCT1),
                 ("Sub-supply to watch", f'=COUNTIFS({DC}!B2:B,"Watch",{DC}!AC2:AC,"sub-supply to the winner")', INT)])
section(tab, S, 7, 1, 4, "Pursue deals by route"); section(tab, S, 7, 6, 9, "Pursue deals by region")
put(tab, "A8", [[f"=QUERY({DC}!A2:AE,\"select AC, count(A), sum(C), avg(E) where B = 'Pursue' group by AC order by sum(C) desc label AC 'Route', count(A) 'Deals', sum(C) 'Expected value (USD)', avg(E) 'Avg win probability'\",0)"]])
put(tab, "F8", [[f"=QUERY({DC}!A2:AE,\"select AB, count(A), sum(C), avg(L) where B = 'Pursue' group by AB order by sum(C) desc label AB 'Region', count(A) 'Deals', sum(C) 'Expected value (USD)', avg(L) 'Avg net margin'\",0)"]])
header(S, 8, 1, 4); header(S, 8, 6, 9)
numfmt(S, 9, 20, 3, 3, USD, "CURRENCY"); numfmt(S, 9, 20, 4, 4, PCT, "PERCENT"); numfmt(S, 9, 22, 8, 8, USD, "CURRENCY"); numfmt(S, 9, 22, 9, 9, PCT1, "PERCENT")
section(tab, S, 24, 1, 9, "Pursue deals by sector")
put(tab, "A25", [[f"=QUERY({DC}!A2:AE,\"select T, count(A), sum(C), avg(L), avg(E) where B = 'Pursue' group by T order by sum(C) desc label T 'Sector', count(A) 'Deals', sum(C) 'Expected value (USD)', avg(L) 'Avg net margin', avg(E) 'Avg win probability'\",0)"]])
header(S, 25, 1, 5); numfmt(S, 26, 52, 3, 3, USD, "CURRENCY"); numfmt(S, 26, 52, 4, 4, PCT1, "PERCENT"); numfmt(S, 26, 52, 5, 5, PCT, "PERCENT")
section(tab, S, 54, 1, 10, "Top 30 deals by priority value")
put(tab, "A55", [["Country", "Opportunity", "Route", "Deal value (USD)", "Net margin", "Win prob.", "Expected value", "Priority value", "Deadline", "Why"]])
put(tab, "A56", [[f"=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{DC}!S2:S,{DC}!W2:W,{DC}!AC2:AC,{DC}!F2:F,{DC}!L2:L,{DC}!E2:E,{DC}!C2:C,{DC}!AE2:AE,{DC}!X2:X,{DC}!Z2:Z}},{DC}!B2:B=\"Pursue\"),8,FALSE),30,10),\"Waiting for the next refresh\")"]])
header(S, 55, 1, 10)
numfmt(S, 56, 86, 4, 4, USD, "CURRENCY"); numfmt(S, 56, 86, 5, 5, PCT1, "PERCENT"); numfmt(S, 56, 86, 6, 6, PCT, "PERCENT")
numfmt(S, 56, 86, 7, 8, USD, "CURRENCY"); numfmt(S, 56, 86, 9, 9, DATE, "DATE")

# ------------------------------------------------------------------ Commodities
S = 51; tab = "Commodities"
base(S, 120, 9); widths(S, [300, 120, 120, 120, 120, 110, 110, 200, 200])
title(tab, S, 9, "Commodities - prices and trends that move the deals",
      "World Bank monthly prices per commodity group (used in the deal calculation) and the live prices of the Commodities Tracker.")
kpis(tab, S, 4, [("Groups rising", f'=COUNTIF({PT}!B2:B,"rising*")', INT), ("Groups falling", f'=COUNTIF({PT}!B2:B,"falling*")', INT),
                 ("Tracked prices", f"=COUNTA({CP}!A2:A)", INT), ("Latest price date", f"=MAX({CP}!G2:G)", DATE)])
section(tab, S, 7, 1, 6, "Price signals by commodity group (3-month change)")
put(tab, "A8", [["Commodity group", "Signal", "1 month %", "3 months %", "12 months %", "Series"]])
put(tab, "A9", [[f"=IFERROR(SORT(FILTER({{{PT}!A2:A,{PT}!B2:B,{PT}!C2:C,{PT}!D2:D,{PT}!E2:E,{PT}!F2:F}},{PT}!A2:A<>\"\"),ABS(FILTER({PT}!D2:D,{PT}!A2:A<>\"\")),FALSE),\"Waiting for the next refresh\")"]])
header(S, 8, 1, 6); numfmt(S, 9, 26, 3, 5, '0.0"%"')
section(tab, S, 28, 1, 7, "Biggest 3-month moves - World Bank series")
put(tab, "A29", [["Series", "Group", "Unit", "Price", "1 month %", "3 months %", "12 months %"]])
put(tab, "A30", [[f"=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{PS}!B2:B,{PS}!A2:A,{PS}!C2:C,{PS}!E2:E,{PS}!F2:F,{PS}!G2:G,{PS}!H2:H}},{PS}!B2:B<>\"\"),ABS(FILTER({PS}!G2:G,{PS}!B2:B<>\"\")),FALSE),20,7),\"Waiting for the next refresh\")"]])
header(S, 29, 1, 7); numfmt(S, 30, 50, 4, 4, "#,##0.00"); numfmt(S, 30, 50, 5, 7, '0.0"%"')
section(tab, S, 52, 1, 6, "Benchmark prices - exchange and official sources (Commodities Tracker)")
put(tab, "A53", [[f"=IFERROR(QUERY({CP}!A2:J,\"select C, D, E, G, H, I where I starts with 'T1' or I starts with 'T2' limit 60 label C 'Commodity', D 'Price (USD)', E 'Unit', G 'Date', H 'Source', I 'Quality'\",0),\"Waiting for the next refresh\")"]])
header(S, 53, 1, 6); numfmt(S, 54, 115, 2, 2, "#,##0.00"); numfmt(S, 54, 115, 4, 4, DATE, "DATE")
for col, cond, color in ((2, "rising", "B42318"), (2, "falling", "0B6E4F")):
    req.append({"addConditionalFormatRule": {"rule": {"ranges": [rng(S, 9, 26, col, col)], "booleanRule": {
        "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": cond}]},
        "format": {"textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": rgb(color)}}}}}, "index": 0}})

# ------------------------------------------------------------------ Buyers
S = 52; tab = "Buyers"
base(S, 90, 7); widths(S, [380, 80, 230, 110, 140, 300, 240])
title(tab, S, 7, "Buyers - who buys, how often and when next",
      "Award history per buyer from all award sources, with the next expected purchase. Refreshed every 4 hours.")
kpis(tab, S, 4, [("Repeat buyers", f"=COUNTA({RB}!A2:A)", INT),
                 ("Expected in 60 days", f'=COUNTIFS({RB}!H2:H,">="&TODAY(),{RB}!H2:H,"<="&(TODAY()+60))', INT),
                 ("Awards tracked", "=COUNTA(Awards!A2:A)", INT)])
section(tab, S, 7, 1, 7, "Expected to buy in the next 60 days")
put(tab, "A8", [["Buyer", "Country", "Commodity group", "Awards (12 months)", "Next expected", "Current suppliers", "Buyer email"]])
put(tab, "A9", [[f"=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{RB}!A2:A,{RB}!B2:B,{RB}!C2:C,{RB}!D2:D,{RB}!H2:H,{RB}!I2:I,{RB}!K2:K}},{RB}!H2:H>=TODAY(),{RB}!H2:H<=TODAY()+60),5,TRUE),25,7),\"None\")"]])
header(S, 8, 1, 7); numfmt(S, 9, 34, 5, 5, DATE, "DATE")
section(tab, S, 36, 1, 6, "Most active buyers (awards in the last 12 months)")
put(tab, "A37", [[f"=IFERROR(QUERY({RB}!A2:O,\"select A, B, C, D, E, M where A is not null order by D desc limit 30 label A 'Buyer', B 'Country', C 'Commodity group', D 'Awards (12 months)', E 'Total awarded (USD)', M 'Median award (USD)'\",0),\"\")"]])
header(S, 37, 1, 6); numfmt(S, 38, 68, 5, 6, USD, "CURRENCY")

# ------------------------------------------------------------------ Assumptions (rebuilt)
S = 15; tab = "Assumptions"
base(S, 90, 11); widths(S, [260, 120, 120, 120, 120, 120, 120, 120, 230, 110, 120])
title(tab, S, 11, "Assumptions - freight, duties and deal settings",
      "Freight indicators and duty rates are checked every morning by the assumptions agent (source and date on every line). Use the Override column to force your own value.")
section(tab, S, 4, 1, 7, "Freight indicators (live)")
put(tab, "A5", [["Indicator", "Value", "Unit", "Change vs previous", "Source", "As of", "Link"]] + [[x, "", u, "", "", "", ""] for x, u in [
    ("Drewry WCI composite", "USD/40ft"), ("Drewry WCI Shanghai - Rotterdam", "USD/40ft"), ("Drewry WCI Shanghai - Genoa", "USD/40ft"),
    ("Drewry WCI Shanghai - Los Angeles", "USD/40ft"), ("Drewry WCI Shanghai - New York", "USD/40ft"), ("Freightos FBX global", "USD/40ft"),
    ("Baltic Dry Index", "points"), ("Bunker VLSFO Singapore", "USD/t"), ("Brent crude", "USD/bbl")]])
header(S, 5, 1, 7)
section(tab, S, 16, 1, 9, "Freight estimate by destination region (from China / East Asia)")
regions = [("Europe", 60), ("Israel", 55), ("Middle East & North Africa", 45), ("Sub-Saharan Africa", 70), ("North America", 75),
           ("Latin America", 80), ("South Asia", 30), ("East Asia", 25), ("Southeast Asia", 25), ("CIS & Central Asia", 90),
           ("Oceania", 60), ("Other", 70)]
put(tab, "A17", [["Destination region", "40ft container (USD)", "Container per tonne (USD/t)", "Dry bulk (USD/t)", "Transit (days)",
                  "Basis / source", "As of", "Override (USD/t)", "Used (USD/t)"]] +
    [[n, "", v, "", "", "previous estimate", "", "", f"=IF(H{18 + i}<>\"\",H{18 + i},C{18 + i})"] for i, (n, v) in enumerate(regions)])
header(S, 17, 1, 9); numfmt(S, 18, 29, 2, 4, "$#,##0", "CURRENCY"); numfmt(S, 18, 29, 8, 9, "$#,##0", "CURRENCY")
section(tab, S, 31, 1, 11, "Import duties by commodity group (MFN applied, simple average % of customs value)")
groups = [("Meat & livestock", .12, .07), ("Fish & seafood", .08, .07), ("Dairy & eggs", .10, .06), ("Fruit, vegetables & nuts", .08, .08),
          ("Cereals, rice & flour", .05, .05), ("Oilseeds, vegetable oils & fats", .05, .05), ("Sugar, coffee, tea, cocoa & spices", .05, .07),
          ("Animal feed", .03, .05), ("Beverages & tobacco", .10, .08), ("Fuels & energy", 0, .03), ("Minerals, cement, aggregates & glass", .03, .08),
          ("Chemicals", .05, .08), ("Fertilizers", 0, .05), ("Plastics & rubber", .06, .07), ("Wood, pulp & paper", .03, .06),
          ("Textiles, fibres & hides", .08, .08), ("Iron & steel", .03, .05), ("Non-ferrous metals", .02, .03), ("Precious metals & stones", 0, .01)]
put(tab, "A32", [["Commodity group", "Israel", "EU", "USA", "Saudi Arabia (GCC)", "India", "Kenya (EAC)", "Nigeria (ECOWAS)",
                  "Basis / source", "As of", "Generic estimate"]] +
    [[g, "", "", "", "", "", "", "", "", "", d] for g, d, _ in groups])
header(S, 32, 1, 11); numfmt(S, 33, 51, 2, 8, "0.0%", "PERCENT"); numfmt(S, 33, 51, 11, 11, "0.0%", "PERCENT")
section(tab, S, 53, 1, 3, "Deal settings")
put(tab, "A54", [["Setting", "Value", "Note"], ["Insurance (% of CIF value)", "0.5%", ""], ["Default number of competitors when unknown", "3", ""],
                 ["Cost of capital (a year)", "10%", "used to finance goods until the buyer pays"], ["Bid and performance bond fees", "0.3%", "share of revenue"],
                 ["Pursuit cost - international tender (USD)", "3000", ""], ["Pursuit cost - Israeli tender (USD)", "1500", ""],
                 ["Pursuit cost - planned notice (USD)", "1000", ""], ["Local partner share (margin points)", "3%", "when the route is via a local partner"]])
header(S, 54, 1, 3)
section(tab, S, 64, 1, 3, "Default gross margin by commodity group")
put(tab, "A65", [["Commodity group", "Default gross margin", "Note"]] + [[g, m, ""] for g, _, m in groups])
header(S, 65, 1, 3); numfmt(S, 66, 84, 2, 2, "0.0%", "PERCENT")
fmt(rng(S, 18, 29, 8, 8), {"backgroundColorStyle": {"rgbColor": rgb("FFF7D6")}}, "userEnteredFormat.backgroundColorStyle")

# ------------------------------------------------------------------ dividers
DIV = [(53, "ANALYSIS", "Analysis: each tab summarizes one kind of data (markets, Israel, deals, commodities, buyers, intelligence)."),
       (54, "RAW DATA", "Raw data: filled automatically by the pipeline. Read and filter freely, do not edit."),
       (55, "SETTINGS", "Settings and operations: your preferences, partners, assumptions, the research worker's queue and the guide.")]
for sid, name, text in DIV:
    base(sid, 6, 4); widths(sid, [900, 50, 50, 50])
    put(name, "A1", [[text]])
    fmt(rng(sid, 1, 6, 1, 4), {"backgroundColorStyle": {"rgbColor": rgb("F5F7FA")}}, "userEnteredFormat.backgroundColorStyle")
    fmt(rng(sid, 1, 1, 1, 1), {"textFormat": {"bold": True, "fontSize": 14, "foregroundColorStyle": {"rgbColor": rgb(NAVY)}}, "wrapStrategy": "WRAP"},
        "userEnteredFormat(textFormat,wrapStrategy)")
    height(sid, 1, 60)

# ------------------------------------------------------------------ tab order, colors, visibility
ORDER = [(45, NAVY), (31, NAVY), (47, NAVY), (24, NAVY), (28, NAVY),
         (53, BLACK), (48, TEAL), (49, TEAL), (50, TEAL), (51, TEAL), (52, TEAL), (29, TEAL), (13, TEAL), (18, TEAL),
         (54, BLACK), (1, GRAY), (41, GRAY), (40, GRAY), ("@sheet:Upcoming", GRAY), (8, GRAY), (9, GRAY), (43, GRAY),
         (55, BLACK), (19, AMBER), (46, AMBER), (15, AMBER), (26, AMBER), (25, AMBER)]
for i, (sid, color) in enumerate(ORDER):
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "index": i, "hidden": False, "tabColorStyle": {"rgbColor": rgb(color)}},
                                          "fields": "index,hidden,tabColorStyle"}})
for sid in (42, 44):  # Price Trends / Price Series: analysed in Commodities
    req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "hidden": True}, "fields": "hidden"}})

if "--create" in sys.argv:
    for sid, name in [(48, "Markets"), (49, "Israel Overview"), (50, "Deals"), (51, "Commodities"), (52, "Buyers"),
                      (53, "ANALYSIS"), (54, "RAW DATA"), (55, "SETTINGS")]:
        pre.append({"addSheet": {"properties": {"sheetId": sid, "title": name}}})
out = {"pre_requests": pre, "clear": ["'Assumptions'!A1:Z200"], "values": values, "requests": req}
Path(__file__).with_name("layout.json").write_text(json.dumps(out, ensure_ascii=False))
print(len(values), "value ranges,", len(req), "requests,", len(pre), "new tabs")
