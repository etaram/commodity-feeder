"""Probe sites with incomplete TLS chains using AIA chasing (fetch the missing intermediate, keep verification on)."""
import pathlib, ssl, traceback
import requests
out = pathlib.Path("data/probe"); out.mkdir(parents=True, exist_ok=True)
URLS = {
    "x_ge": "https://odapi.spa.ge/api/releases.json?page=1",
    "x_md": "https://public.mtender.gov.md/tenders/?offset=2026-10-20T00:00:00Z",
    "x_qa": "https://monaqasat.mof.gov.qa/TendersOnlineServices/AvailableMinistriesTenders/1",
    "x_tr": "https://www.ilan.gov.tr/ilan/kategori/9/ihale-duyurulari",
}
try:
    from aia import AIASession
    aia = AIASession()
except Exception as e:
    aia = None; print("aia missing", e)
for name, url in URLS.items():
    try:
        import tempfile, os
        cadata = aia.cadata_from_url(url)
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False); f.write(cadata); f.close()
        import certifi
        bundle = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        bundle.write(open(certifi.where()).read() + "\n" + cadata); bundle.close()
        r = requests.get(url, timeout=60, verify=bundle.name, headers={"User-Agent": "Mozilla/5.0"})
        (out / f"{name}.txt").write_bytes(f"STATUS: {r.status_code}\nTYPE: {r.headers.get('content-type')}\n\n".encode() + r.content[:1_500_000])
        print(name, r.status_code, len(r.content))
    except Exception as e:
        (out / f"{name}.txt").write_text(f"ERROR: {e}\n{traceback.format_exc()[-800:]}"); print(name, "ERR", e)
