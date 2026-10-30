import re, sys, pathlib, requests
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
out = pathlib.Path("data/leads/probe_html"); out.mkdir(parents=True, exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = UA
base = "https://eprocure.gov.in"
def get(url, name):
    r = s.get(url, timeout=40); (out / name).write_text(r.text[:200000], encoding="utf-8"); print(name, r.status_code, len(r.text), r.url); return r.text
get(base + "/eprocure/app", "in0.html")
d = get(base + "/eprocure/app?page=FrontEndListTendersbyDate&service=page", "in_bydate.html")
o = get(base + "/eprocure/app?page=FrontEndTendersByOrganisation&service=page", "in_byorg.html")
links = re.findall(r'href="([^"]*DirectLink[^"]*)"', o)
print("org links", len(links), links[:3])
if links:
    u = links[0].replace("&amp;", "&"); u = u if u.startswith("http") else base + u
    o2 = get(u, "in_org1.html")
    l2 = re.findall(r'href="([^"]*DirectLink[^"]*)"', o2); print("l2", len(l2), l2[:3])
    if l2:
        u = l2[0].replace("&amp;", "&"); u = u if u.startswith("http") else base + u
        get(u, "in_org2.html")
