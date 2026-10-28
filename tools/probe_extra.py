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
    base = {"PageIndex": 0, "PageSize": 50, "Title": "", "Description": "", "Reference": "", "PublishedFrom": "",
            "PublishedTo": "", "DeadlineFrom": "", "DeadlineTo": "", "Countries": [], "Agencies": [], "UNSPSCs": [],
            "NoticeTypes": [], "SortField": "DatePublished", "SortAscending": False, "isPicker": False,
            "IsSustainable": False, "IsActive": True, "NoticeDisplayType": None,
            "NoticeSearchTotalLabelId": "noticeSearchTotal", "TypeOfCompetitions": []}
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.ungm.org/Public/Notice",
           "Origin": "https://www.ungm.org", "__RequestVerificationToken": tok, "RequestVerificationToken": tok}
    for i, (url, kw) in enumerate([
        ("https://www.ungm.org/Public/Notice/Search", {"json": base}),
        ("https://www.ungm.org/Public/Notice/Search", {"data": json.dumps(base), "headers2": {"Content-Type": "application/json; charset=UTF-8"}}),
        ("https://www.ungm.org/Public/Notice/Search", {"json": dict(base, DeadlineFrom="28-Oct-2026")}),
    ]):
        h = dict(hdr); h.update(kw.pop("headers2", {}))
        try:
            r = s.post(url, headers=h, timeout=60, **kw); save(f"x_ungm_{i}", r, url)
        except Exception as e:
            print("ungm", i, e)

def other():
    s = cr.Session(impersonate="chrome")
    for name, method, url, body in [
        ("x_prozorro_search", "POST", "https://prozorro.gov.ua/api/search/tenders", {"status": ["active.tendering"], "value": {"from": 20000000}, "page": 1}),
        ("x_prozorro_search_get", "GET", "https://prozorro.gov.ua/api/search/tenders?status=active.tendering&value.from=20000000&page=1", None),
        ("x_etimad", "GET", "https://tenders.etimad.sa/Tender/AllSupplierTendersForVisitorAsync?PageSize=24&PageNumber=1", None),
        ("x_aiib", "GET", "https://www.aiib.org/en/opportunities/business/project-procurement/_common/ppo-2026.js", None),
        ("x_isdb", "GET", "https://www.isdb.org/project-procurement/tenders?status=active", None),
        ("x_afdb_rss", "GET", "https://www.afdb.org/en/documents/project-related-procurement/procurement-notices/specific-procurement-notices/rss.xml", None),
    ]:
        try:
            r = s.post(url, json=body, timeout=60) if method == "POST" else s.get(url, timeout=60)
            save(name, r, url)
        except Exception as e:
            print(name, e)

for f in (ungm, other):
    try: f()
    except Exception: traceback.print_exc()
