"""Session-based probes (UNGM, Prozorro search, Etimad async)."""
import json, pathlib, re, traceback
from curl_cffi import requests as cr
out = pathlib.Path("data/probe"); out.mkdir(parents=True, exist_ok=True)

def save(name, r, note=""):
    (out / f"{name}.txt").write_bytes(f"STATUS: {getattr(r,'status_code','')}\nNOTE: {note}\nTYPE: {getattr(r,'headers',{}).get('content-type','')}\n\n".encode() + (r.content[:2_000_000] if hasattr(r,'content') else str(r).encode()))
    print(name, getattr(r, "status_code", ""), len(getattr(r, "content", b"")))

def ungm():
    s = cr.Session(impersonate="chrome")
    g = s.get("https://www.ungm.org/Public/Notice", timeout=60)
    tok = re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', g.text)
    tok = tok.group(1) if tok else ""
    base = {"PageIndex": 0, "PageSize": 15, "Title": "", "Description": "", "Reference": "", "PublishedFrom": "",
            "PublishedTo": "", "DeadlineFrom": "", "DeadlineTo": "", "Countries": [], "Agencies": [], "UNSPSCs": [],
            "NoticeTypes": [], "SortField": "Deadline", "SortAscending": True, "isPicker": False,
            "IsSustainable": False, "IsActive": True, "NoticeDisplayType": None,
            "NoticeSearchTotalLabelId": "noticeSearchTotal", "TypeOfCompetitions": []}
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.ungm.org/Public/Notice",
           "Origin": "https://www.ungm.org", "__RequestVerificationToken": tok, "RequestVerificationToken": tok}
    print("cookies", list(s.cookies.keys()), "tok", tok[:10])
    for i, (url, kw) in enumerate([
        ("https://www.ungm.org/Public/Notice/Search", {"json": base}),
        ("https://www.ungm.org/Public/Notice/Search", {"data": json.dumps(base), "headers2": {"Content-Type": "application/json; charset=UTF-8"}}),
        ("https://www.ungm.org/Public/Notice/Search", {"data": json.dumps(base, separators=(",", ":")), "headers2": {"Content-Type": "application/json"}}),
        ("https://www.ungm.org/Public/Notice/SearchEOI", {"json": base}),
    ]):
        h = dict(hdr); h.update(kw.pop("headers2", {}))
        try:
            r = s.post(url, headers=h, timeout=60, **kw); save(f"x_ungm_{i}", r, url)
        except Exception as e:
            print("ungm", i, e)

def other():
    s = cr.Session(impersonate="chrome")
    for name, method, url, body in [
        ("x_pz_feed", "GET", "https://public-api.prozorro.gov.ua/api/2.5/tenders?descending=1&limit=100&opt_fields=status,value,title,procurementMethodType,mainProcurementCategory,tenderID,tenderPeriod,procuringEntity", None),
        ("x_pz_one", "GET", "https://public-api.prozorro.gov.ua/api/2.5/tenders?descending=1&limit=5", None),
    ]:
        try:
            r = s.post(url, json=body, timeout=60) if method == "POST" else s.get(url, timeout=60)
            save(name, r, url)
        except Exception as e:
            print(name, e)

for f in (ungm, other):
    try: f()
    except Exception: traceback.print_exc()
