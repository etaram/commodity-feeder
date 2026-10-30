import subprocess, sys, re, time, datetime as dt, requests, io, csv
def sh(c, t=900):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t); return (r.stdout + r.stderr)[-600:]
sh(f"{sys.executable} -m pip install -q 'scrapling[fetchers]'"); sh("scrapling install")
H = {"User-Agent": "Mozilla/5.0"}
print("## MEXICO datos.gob.mx procedimientos_contratacion")
try:
    d = requests.get("https://datos.gob.mx/api/3/action/package_show", params={"id": "procedimientos_contratacion"}, headers=H, timeout=40).json()["result"]
    for x in d["resources"][:6]:
        print(" res", x.get("format"), x.get("size"), x.get("last_modified"), x["url"][:140])
    u = next((x["url"] for x in d["resources"] if (x.get("format") or "").upper() == "CSV"), None)
    if u:
        r = requests.get(u, headers=H, timeout=120, stream=True)
        raw = b"".join(c for _, c in zip(range(40), r.iter_content(65536)))
        txt = raw.decode("utf-8", "replace")
        print(" status", r.status_code, "bytes read", len(raw))
        rows = list(csv.reader(io.StringIO(txt)))
        print(" header:", rows[0][:30]); print(" sample:", rows[1][:30] if len(rows) > 1 else None)
except Exception as e:
    print(" ERR", type(e).__name__, str(e)[:200])
from scrapling.fetchers import Fetcher, StealthyFetcher
day = (dt.date.today() - dt.timedelta(days=2)).strftime("%Y%m%d")
T = [("taiwan_g0v_api", f"https://pcc.g0v.ronny.tw/api/listbydate?date={day}"),
     ("taiwan_pcc", "https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic"),
     ("tenders_guru_pl", "https://tenders.guru/pl/api/tenders?page=1"),
     ("tenders_guru_hu", "https://tenders.guru/hu/api/tenders?page=1"),
     ("peru_osce_ocds", "https://contratacionesabiertas.osce.gob.pe/"),
     ("peru_datos", "https://www.datosabiertos.gob.pe/"),
     ("argentina_contrataciones", "https://contrataciones.gob.ar/"),
     ("argentina_comprar", "https://comprar.gob.ar/"),
     ("indonesia_inaproc", "https://inaproc.id/"),
     ("singapore_gebiz", "https://www.gebiz.gov.sg/")]
for k, u in T:
    for name, fn in [("Fetcher", lambda u: Fetcher.get(u, impersonate="chrome", timeout=40, verify=False)),
                     ("Stealthy", lambda u: StealthyFetcher.fetch(u, headless=True, network_idle=True, solve_cloudflare=True, timeout=90000))]:
        t0 = time.time()
        try:
            p = fn(u); body = p.html_content if hasattr(p, "html_content") else str(p.body)
            cf = bool(re.search(r"Just a moment|cf-chl|Attention Required", body))
            print(f"{k} {name}: status={p.status} len={len(body)} cloudflare_page={cf} {time.time()-t0:.0f}s | {re.sub(r'\\s+', ' ', body[:160])!r}")
        except Exception as e:
            print(f"{k} {name}: ERR {type(e).__name__} {str(e)[:110]}")
