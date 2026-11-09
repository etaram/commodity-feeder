"""Find or fetch free stock media for the brand film (runs on a GitHub runner, which has open internet).
Sources: Wikimedia Commons (licence read from file metadata) and NASA (public domain).
  scout <queries.json> <out>  -> per hit: 3 preview frames + meta.json (nothing large is kept)
  fetch <picks.json>  <out>   -> download chosen files, trim and transcode to H.264
"""
import json, os, re, subprocess, sys, urllib.parse, urllib.request
UA = {"User-Agent": "SinderFilmBot/1.0 (brand film research; contact via github etaram)"}
OK_LIC = re.compile(r"^(cc0|public domain|pd|cc by(?!-nc)(-sa)? ?[0-9.]*|cc-by(-sa)?-[0-9.]+)", re.I)

def get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()

def commons(q, kind, n):
    ft = "video" if kind == "video" else "bitmap"
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{q} filetype:{ft}", "gsrnamespace": 6, "gsrlimit": 40, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280})
    pages = json.loads(get(u)).get("query", {}).get("pages", {})
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]; md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName", {}).get("value") or "").strip()
        if not OK_LIC.match(lic): continue
        if kind == "video" and (ii.get("height", 0) < 720 or ii.get("size", 0) > 600e6): continue
        if kind == "image" and ii.get("width", 0) < 2400: continue
        art = re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", ""))[:120]
        out.append({"src": "commons", "title": p["title"], "url": ii["url"], "thumb": ii.get("thumburl"), "w": ii.get("width"), "h": ii.get("height"),
                    "dur": ii.get("duration"), "license": lic, "author": art.strip(), "page": ii.get("descriptionurl")})
        if len(out) >= n: break
    return out

def nasa(q, kind, n):
    u = "https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": q, "media_type": "video" if kind == "video" else "image"})
    items = json.loads(get(u))["collection"]["items"][:n * 2]; out = []; print("nasa hits", q, len(items))
    for it in items:
        d = it["data"][0]
        try: assets = [a if isinstance(a, str) else a.get("href") for a in json.loads(get(it["href"]))]
        except Exception as e: print("nasa manifest", e); continue
        print("nasa assets", d.get("nasa_id"), [a.rsplit("/", 1)[-1] for a in assets][:8])
        if kind == "video": pick = next((a for a in assets if a.endswith("~orig.mp4")), None) or next((a for a in assets if a.endswith(".mp4")), None)
        else: pick = next((a for a in assets if re.search(r"~orig\.(jpg|png)$", a)), None) or next((a for a in assets if re.search(r"~large\.(jpg|png)$", a)), None)
        if not pick: continue
        out.append({"src": "nasa", "title": d.get("title"), "url": pick.replace("http://", "https://"), "license": "Public domain (NASA)",
                    "author": d.get("center", "NASA"), "page": f"https://images.nasa.gov/details/{d.get('nasa_id')}"})
        if len(out) >= n: break
    return out

def frames(src, dst_prefix, dur=None):
    ts = [0.15, 0.5, 0.85]
    for i, f in enumerate(ts):
        at = (dur or 10) * f
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", src, "-frames:v", "1", "-vf", "scale=480:-2", "-threads", "1", "-pix_fmt", "yuvj420p", "-q:v", "4", f"{dst_prefix}_{i}.jpg"])

def scout(qfile, out):
    os.makedirs(out, exist_ok=True); meta = []
    for q in json.load(open(qfile)):
        try: hits = (nasa if q.get("src") == "nasa" else commons)(q["q"], q["kind"], q.get("n", 6))
        except Exception as e: print("search failed", q, e); continue
        for j, h in enumerate(hits):
            key = f"{q['id']}_{j}"; h["key"] = key; h["query"] = q["q"]
            try:
                if q["kind"] == "image":
                    open(f"{out}/{key}_0.jpg", "wb").write(get(h["thumb"] or h["url"]))
                else:
                    tmp = f"/tmp/{key}"; probe_url = h["url"]
                    # read only the first ~25 MB, enough for preview frames
                    subprocess.run(["curl", "-sL", "-A", UA["User-Agent"], "-r", "0-60000000", "-o", tmp, probe_url], timeout=300)
                    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", tmp], capture_output=True, text=True).stdout.strip()
                    h["probe_dur"] = d; frames(tmp, f"{out}/{key}", min(float(h.get("dur") or d or 10), float(d or 10)))
                    os.remove(tmp)
                meta.append(h); print("ok", key, h["title"][:80])
            except Exception as e: print("skip", key, e)
    json.dump(meta, open(f"{out}/meta.json", "w"), indent=1)

def fetch(pfile, out):
    os.makedirs(out, exist_ok=True)
    for p in json.load(open(pfile)):
        tmp = f"/tmp/{p['name']}.src"; subprocess.run(["curl", "-sL", "-A", UA["User-Agent"], "-o", tmp, p["url"]], timeout=900, check=True)
        if p.get("kind") == "image":
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-vf", "scale='min(3200,iw)':-2", "-q:v", "2", f"{out}/{p['name']}.jpg"], check=True)
        else:
            ss, du = str(p.get("ss", 0)), str(p.get("dur", 8))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", ss, "-i", tmp, "-t", du, "-an", "-vf", "scale=-2:'min(2160,ih)',fps=30",
                            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", f"{out}/{p['name']}.mp4"], check=True)
        os.remove(tmp); print("fetched", p["name"])
    json.dump(json.load(open(pfile)), open(f"{out}/credits.json", "w"), indent=1)

if __name__ == "__main__":
    {"scout": scout, "fetch": fetch}[sys.argv[1]](sys.argv[2], sys.argv[3])
