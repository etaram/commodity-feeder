"""Source probe: fetch each public URL in urls.txt once from the company server and print what came back (status,
content type, size, API paths found in a JS bundle, and the first characters of the body). Used to learn the shape
of a new public tender source before writing its collector. Public notice pages only; no sign-in, no forms, no
CAPTCHA. One request per URL. Output is short so the public workflow log carries no bulk data."""
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
API = re.compile(r'["\'`](/?(?:webapi/)?api/[A-Za-z0-9_/\-]{2,60}|/Home/[A-Za-z0-9_]{3,50}|/PublicPortal/[A-Za-z0-9_]{3,60})')


def one(line):
    data, grep = None, ""
    if line.startswith("POST "):                       # POST <url> <chars> <json body>
        _, url, n, body = line.split(" ", 3)
        data, n = body.encode(), int(n)
    else:
        parts = line.split()
        url, n = parts[0], int(parts[1]) if len(parts) > 1 else 500
        grep = next((x[5:] for x in parts[2:] if x.startswith("grep=")), "")
    try:
        hd = {"User-Agent": UA, "Accept": "*/*", "X-Requested-With": "XMLHttpRequest"}
        if data:
            hd["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=hd)
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read(3_000_000)
            st, ct = r.status, r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        body, st, ct = e.read(2000), e.code, e.headers.get("content-type", "")
    except Exception as e:  # noqa: BLE001
        print(f"== {url}\n   ERROR {type(e).__name__}: {str(e)[:160]}")
        return
    t = body.decode("utf-8", "replace")
    print(f"== {url}\n   {st} {ct} {len(body)} bytes")
    tot = re.findall(r'"(total[A-Za-z]*|count|totalCount)"\s*:\s*(\d+)', t)
    if tot:
        print("   totals:", tot[:5])
    if url.endswith(".js"):
        print("   paths:", sorted(set(API.findall(t)))[:60])
        print("   templated:", sorted(set(re.findall(r"\$\{[A-Za-z0-9_$]{1,8}\}(/[A-Za-z0-9_/]{3,60}\??[A-Za-z_=&${}]{0,80})", t)))[:80])
        print("   urls:", sorted(set(re.findall(r"[\"'`](https?://[^\"'`\s]{6,120}|/(?:api|rest|services|ws|b_ihalearama|ihale)[^\"'`\s]{2,100})[\"'`]", t)))[:80])
        for m in list(re.finditer(r'queryKey:\["tenders"|GetTenders|/search[A-Za-z]*\(|ihaleAra|SearchIhale|apiUrl|baseUrl|procedimientos|whitney', t))[:6]:
            print("   ..." + re.sub(r"\s+", " ", t[max(0, m.start() - 100):m.start() + 400]))
        return
    print("   scripts:", re.findall(r'<script[^>]+src="([^"]+)"', t)[:15])
    if grep:
        try:
            found = list(re.finditer(grep, t))[:8]
        except re.error as e:
            print("   bad grep pattern:", e); found = []
        for m in found:
            print("   >>" + re.sub(r"\s+", " ", t[max(0, m.start() - 150):m.start() + max(350, len(m.group(0)) + 50)]))
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"\s+", " ", t)
    print("   " + t[:n])


for ln in open(sys.argv[1], encoding="utf-8"):
    ln = ln.strip()
    if ln and not ln.startswith("#"):
        one(ln)
