import json, pathlib, re, requests
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 commodity-feeder probe"
out = []
for u in ["https://data.open-contracting.org/en/", "https://data.open-contracting.org/en/search/",
          "https://data.open-contracting.org/api/publications"]:
    r = s.get(u, timeout=60)
    out.append(f"== {u} {r.status_code} {r.headers.get('content-type')} {len(r.text)}")
    out.append(r.text[:200])
    out.append(" ".join(sorted(set(re.findall(r"publication/(\d+)", r.text)))))
    for m in re.finditer(r'href="/en/publication/(\d+)"[^>]*>(.*?)</a>', r.text, re.S):
        out.append(f"{m.group(1)}\t{re.sub(r'<[^>]+>|\s+', ' ', m.group(2)).strip()[:150]}")
pathlib.Path("data/probe/ocdr.txt").write_text("\n".join(out))
