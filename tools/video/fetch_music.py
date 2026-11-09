"""Find candidate music beds on Openverse (CC0 / CC BY only, commercial use allowed) and download them with their credits. Runs in Actions."""
import json, pathlib, sys, time, urllib.parse, urllib.request
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "SinderVideo/1.0"}
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=60)
seen, picks = set(), []
import os
Q = os.environ.get("MUSIC_Q", "dark electronic|tech house|cinematic trailer|synthwave|hip hop instrumental|future bass|deep house|epic trailer|electronic pulse|cyberpunk").split("|")
for q in Q:
    u = "https://api.openverse.org/v1/audio/?" + urllib.parse.urlencode({"q": q, "license": "cc0,by", "category": "music", "page_size": 20})
    try: res = json.load(get(u)).get("results", [])
    except Exception as e: print("search fail", q, e); continue
    for r in res:
        d = (r.get("duration") or 0) / 1000
        if r["id"] in seen or not (55 <= d <= 240) or not r.get("url"): continue
        seen.add(r["id"]); picks.append({"id": r["id"], "q": q, "title": r.get("title"), "creator": r.get("creator"), "license": r.get("license"), "license_version": r.get("license_version"), "source": r.get("source"), "landing": r.get("foreign_landing_url"), "url": r["url"], "dur": d, "tags": [t.get("name") for t in (r.get("tags") or [])][:12]})
    time.sleep(1)
print(len(picks), "candidates")
keep = []
for p in picks[:40]:
    ext = p["url"].rsplit(".", 1)[-1].split("?")[0][:4] or "mp3"
    f = out / f"{p['id']}.{ext}"
    try: f.write_bytes(get(p["url"]).read()); p["file"] = f.name; keep.append(p); print("ok", p["title"], p["license"], round(p["dur"]))
    except Exception as e: print("dl fail", p["title"], e)
(out / "music.json").write_text(json.dumps(keep, indent=1))
