"""Probe for the bulk supplier sources (leads/supplier_bulk.py): which public download endpoints answer from the runner.
Prints status codes, sizes, link and endpoint candidates and robots.txt rules only (no records)."""
import re
import sys
import urllib.robotparser

import requests

UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
S = requests.Session()
S.headers["User-Agent"] = UA


def get(url, **kw):
    try:
        r = S.get(url, timeout=kw.pop("timeout", 40), **kw)
        print(f"GET {url} -> {r.status_code} {len(r.content)}B {r.headers.get('content-type', '')[:60]}")
        return r
    except Exception as e:  # noqa: BLE001
        print(f"GET {url} -> ERR {type(e).__name__} {str(e)[:120]}")
        return None


def head(url):
    try:
        r = S.head(url, timeout=40, allow_redirects=True)
        print(f"HEAD {url} -> {r.status_code} len={r.headers.get('content-length')} {r.headers.get('content-type', '')[:50]} last-mod={r.headers.get('last-modified')}")
        return r
    except Exception as e:  # noqa: BLE001
        print(f"HEAD {url} -> ERR {type(e).__name__}")


def robots(base, paths):
    rp = urllib.robotparser.RobotFileParser()
    r = get(base + "/robots.txt", timeout=20)
    if r is not None and r.status_code == 200:
        rp.parse(r.text.splitlines())
        for p in paths:
            print(f"  robots {base}{p}: allowed={rp.can_fetch(UA, base + p)}")
        print("  robots head:", " | ".join(r.text.splitlines()[:25])[:900])


def traces2():
    print("== TRACES2")
    from urllib.parse import urljoin
    r = get("https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/index")
    if r is None:
        return
    print("final url:", r.url)
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', r.text)
    print("scripts:", srcs[:30])
    print("html:", re.sub(r"\s+", " ", r.text[:2500]))
    found = set()
    for s in srcs:
        u = urljoin(r.url, s)
        if "/cas/" in u:
            continue
        j = get(u)
        if j is None or j.status_code != 200:
            continue
        for m in re.finditer(r"[\"'`]([^\"'`\s]{0,100}(publication|listing|/api/|download|export|excel|xlsx|search)[^\"'`\s]{0,100})[\"'`]", j.text, re.I):
            found.add(m.group(1))
    for f in sorted(found)[:300]:
        print("  endpoint?", f)


def denue2():
    print("== DENUE2")
    r = get("https://www.inegi.org.mx/app/descarga/?ti=6")
    if r is not None:
        print("scripts:", re.findall(r'<script[^>]+src="([^"]+)"', r.text)[:20])
        for n, m in enumerate(re.finditer(r"denue|masiva|\.zip|ajax|json", r.text, re.I)):
            if n > 40:
                break
            print("  ctx:", re.sub(r"\s+", " ", r.text[max(0, m.start() - 120): m.end() + 120]))
    for u in ["https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_31-33_csv.zip"]:
        try:
            x = S.get(u, timeout=60, stream=True)
            b = next(x.iter_content(400))
            print(f"STREAM {u} -> {x.status_code} {x.headers.get('content-type')} len={x.headers.get('content-length')} first={b[:120]!r}")
            x.close()
        except Exception as e:  # noqa: BLE001
            print("STREAM ERR", u, type(e).__name__)


def traces3():
    print("== TRACES3")
    j = get("https://webgate.ec.europa.eu/tracesnt/assets/js/min/establishment-listing.8-2-14-20261210-113641000.min.js")
    if j is None:
        return
    t = j.text
    for tok in ["view/search", "view/view", "export/spreadsheet", "downloadXls", "streamPdf", "remoteEstablishmentListingContext",
                "toRemoteUrl", "classificationSectionId", "Restangular", "setBaseUrl", "baseUrl", "sections", "activities", "pageSize", "offset"]:
        for n, m in enumerate(re.finditer(re.escape(tok), t)):
            if n >= 3:
                break
            print(f"  [{tok}]", t[max(0, m.start() - 350): m.end() + 350].replace("\n", " "))
    for u in ["https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/view/search/CN/MEAT",
              "https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/sections",
              "https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/countries"]:
        r = get(u)
        if r is not None:
            print("   body:", r.text[:400].replace("\n", " "))


def traces4():
    print("== TRACES4")
    for u in ["https://webgate.ec.europa.eu/tracesnt/assets/js/min/establishment-listing.8-2-14-20261210-113641000.min.js",
              "https://webgate.ec.europa.eu/tracesnt/assets/js/min/footer.8-2-14-20261210-113641000.min.js"]:
        j = get(u)
        if j is None:
            continue
        t = j.text
        for tok in ["establishmentListingRoute\",", "establishmentListingRoute\"", "appliedClassificationSectionRoute", "contextPath:", "contextPath=",
                    "factory(\"routeService", "allRoute", "restRoute", "/rest/", "\"/api", "streamFile=function", "streamFile:function"]:
            for n, m in enumerate(re.finditer(re.escape(tok), t)):
                if n >= 2:
                    break
                print(f"  [{tok}]", t[max(0, m.start() - 300): m.end() + 400].replace("\n", " "))


def traces():
    print("== TRACES")
    robots("https://webgate.ec.europa.eu", ["/tracesnt/directory/publication/establishment/index", "/tracesnt/api/", "/tracesnt/directory/"])
    r = get("https://webgate.ec.europa.eu/tracesnt/directory/publication/establishment/index")
    if r is None:
        return
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', r.text)
    print("scripts:", srcs[:20])
    print("html head:", re.sub(r"\s+", " ", r.text[:1500]))
    found = set()
    for s in srcs:
        u = s if s.startswith("http") else "https://webgate.ec.europa.eu" + (s if s.startswith("/") else "/tracesnt/directory/publication/establishment/" + s)
        j = get(u)
        if j is None or j.status_code != 200:
            continue
        for m in re.finditer(r"[\"'`]([^\"'`\s]{0,80}(publication|establishment|/api/|download|export)[^\"'`\s]{0,80})[\"'`]", j.text):
            found.add(m.group(1))
    for f in sorted(found)[:200]:
        print("  endpoint?", f)


def denue():
    print("== DENUE")
    robots("https://www.inegi.org.mx", ["/contenidos/masiva/denue/denue_00_31-33_csv.zip", "/app/descarga/"])
    r = get("https://www.inegi.org.mx/app/descarga/?ti=6")
    if r is not None:
        links = sorted(set(re.findall(r"[\w/.:-]*denue[\w/.:-]*\.zip", r.text, re.I)))
        print("zip links:", len(links), links[:60])
    for u in ["https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_31-33_csv.zip",
              "https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_11_csv.zip",
              "https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_43_csv.zip"]:
        head(u)
    r = get("https://www.inegi.org.mx/inegi/terminos.html")
    if r is not None:
        print("terms:", re.sub(r"<[^>]+>|\s+", " ", r.text)[:200])


def fsis():
    print("== FSIS")
    robots("https://www.fsis.usda.gov", ["/inspection/establishments/meat-poultry-and-egg-product-inspection-directory", "/sites/default/files/"])
    r = get("https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory")
    if r is not None:
        links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|zip)[^"]*)"', r.text, re.I)))
        print("file links:", links[:40])
        print("api-like:", sorted(set(re.findall(r'["\'](/[^"\']*(?:api|json|dataset)[^"\']*)["\']', r.text)))[:30])
    get("https://catalog.data.gov/api/3/action/package_search?q=FSIS%20inspection%20directory&rows=5")


def prh():
    print("== PRH")
    robots("https://avoindata.prh.fi", ["/opendata-ytj-api/v3/companies", "/opendata-ytj-api/v3/all_companies"])
    r = get("https://avoindata.prh.fi/opendata-ytj-api/v3/companies?mainBusinessLine=10&page=1")
    if r is not None and r.status_code == 200:
        d = r.json()
        print("keys:", list(d)[:10], "total:", d.get("totalResults"))
        c = (d.get("companies") or [{}])[0]
        print("company keys:", list(c))
        print("forms:", c.get("companyForms"), "mbl:", c.get("mainBusinessLine"), "site:", c.get("website"))
    head("https://avoindata.prh.fi/opendata-ytj-api/v3/all_companies")


if __name__ == "__main__":
    for t in (sys.argv[1:] or ["traces", "denue", "fsis", "prh"]):
        try:
            globals()[t]()
        except Exception as e:  # noqa: BLE001
            print(t, "failed", type(e).__name__, str(e)[:200])
