import pathlib, re, requests
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 commodity-feeder probe"
out = []
for f in ["fmc_oti", "fmc_main", "fmc_vocc"]:
    p = pathlib.Path(f"data/probe/{f}.txt")
    if p.exists():
        t = p.read_text(errors="replace")
        out.append(f"== {f}")
        out += sorted(set(re.findall(r'href=["\']([^"\']+)["\'][^>]*>([^<]{0,80})', t)))[:150]
pathlib.Path("data/probe/fmc_links.txt").write_text("\n".join(map(str, out)))
