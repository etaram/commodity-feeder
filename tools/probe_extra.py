"""Scratch probe: OCP Data Registry - list publications and download sizes (results in data/probe/ocdr.txt)."""
import gzip, io, json, pathlib, re, requests
out = []
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 commodity-feeder probe"
r = s.get("https://data.open-contracting.org/en/", timeout=60)
out.append(f"home {r.status_code} {len(r.text)}")
pubs = dict.fromkeys(re.findall(r'/en/publication/(\d+)"[^>]*>\s*([^<]{3,160})', r.text))
out.append(f"pubs {len(pubs)}")
for pid, title in list(pubs)[:200]:
    out.append(f"{pid}\t{title.strip()}")
for pid in ["120"]:
    p = s.get(f"https://data.open-contracting.org/en/publication/{pid}", timeout=60)
    out.append(f"page {pid} {p.status_code}")
    out.append(" | ".join(sorted(set(re.findall(r"name=([\w.]+)", p.text)))))
    h = s.get(f"https://data.open-contracting.org/en/publication/{pid}/download?name=2023.jsonl.gz", stream=True, timeout=60,
              allow_redirects=True)
    out.append(f"dl {h.status_code} {h.url[:200]} len={h.headers.get('content-length')} type={h.headers.get('content-type')}")
    raw = h.raw.read(200000)
    try:
        txt = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(3000).decode("utf-8", "replace")
    except Exception as e:
        txt = f"gz err {e}"
    out.append(txt[:3000])
pathlib.Path("data/probe/ocdr.txt").write_text("\n".join(out))
print("\n".join(out[:20]))
