import subprocess, sys, re, datetime as dt, json
def sh(c, t=900):
    return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
sh(f"{sys.executable} -m pip install -q 'scrapling[fetchers]'"); sh("scrapling install")
from scrapling.fetchers import Fetcher, StealthyFetcher
def show(tag, p, n=700):
    body = p.html_content if hasattr(p, "html_content") else str(p.body)
    txt = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S))
    print(f"### {tag}: status={p.status} len={len(body)}\n{txt[:n]}\n", flush=True)
    return body
# Mexico CSV through scrapling
for u in ["https://repodatos.atdt.gob.mx/api_update/tecnm/procedimientos_contratacion/procedimientos_contratacion.csv"]:
    for nm, fn in [("Fetcher", lambda u: Fetcher.get(u, impersonate="chrome", timeout=90, verify=False)),
                   ("Stealthy", lambda u: StealthyFetcher.fetch(u, headless=True, timeout=120000))]:
        try:
            p = fn(u); b = show(f"mexico csv {nm}", p, 900)
        except Exception as e:
            print("mexico", nm, "ERR", str(e)[:160], flush=True)
# Taiwan g0v api
day = (dt.date.today() - dt.timedelta(days=2)).strftime("%Y%m%d")
for u in [f"https://pcc.g0v.ronny.tw/api/listbydate?date={day}", "https://pcc.g0v.ronny.tw/api/searchbycompanyname?query=%E9%9B%BB%E5%8A%9B", "https://pcc.g0v.ronny.tw/"]:
    try:
        p = Fetcher.get(u, impersonate="chrome", timeout=60, verify=False); show("taiwan " + u[-40:], p, 900)
    except Exception as e:
        print("taiwan ERR", str(e)[:150], flush=True)
# Indonesia inaproc: look for tender links / api calls
try:
    p = StealthyFetcher.fetch("https://inaproc.id/", headless=True, network_idle=True, timeout=120000)
    b = p.html_content; print("### inaproc links:", sorted(set(re.findall(r'href="(/[^"#]{3,60})"', b)))[:40], flush=True)
    print("### inaproc api hints:", sorted(set(re.findall(r'https?://[a-z0-9.-]*(?:api|lpse)[a-z0-9./_-]*', b)))[:20], flush=True)
except Exception as e:
    print("inaproc ERR", str(e)[:150], flush=True)
# Singapore GeBIZ + data.gov.sg procurement dataset
try:
    p = Fetcher.get("https://data.gov.sg/api/action/package_search?q=gebiz", impersonate="chrome", timeout=60); show("sg ckan", p, 500)
    p = Fetcher.get("https://api-production.data.gov.sg/v2/public/api/datasets?page=1", impersonate="chrome", timeout=60)
    names = re.findall(r'"name":"([^"]*(?:rocurement|ender|GeBIZ)[^"]*)"', p.html_content if hasattr(p, "html_content") else str(p.body)); print("### sg datasets matching:", names[:10], flush=True)
except Exception as e:
    print("sg ERR", str(e)[:150], flush=True)
