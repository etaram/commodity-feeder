"""Supplier enrichment on the company server: the website check (leads/company_check.py, which now also extracts the
profile fields of leads/company_profile.py) run over the whole supplier index in priority order, plus three slow,
rate-limited lanes of free public sources. Runs in a capped, low-priority container (deploy/enrich/_enrich_root.sh),
resumes after a restart, and keeps every result on the server under /opt/sinder/enrich (root only).

Priority (owner, 12 Nov 2026): producers first (manufacturers, producers, farms, growers, co-operatives), then goods
suppliers whose role the site will tell, then traders / distributors / exporters, then contractors and services. Inside
a tier: a website first, then evidence (customs shipments, contract wins, official export records, notable), and the
size buckets are interleaved so mid-size firms are read as early as large ones. Records without a website wait at the end.

Lanes (each writes its own file, so a lane can be stopped or switched off without touching the others):
  site      the company's own site: up to 10 pages, robots.txt respected, one request at a time per host with a pause;
            WeChat QR images the site labels WeChat are fetched (same site, under 400 KB) and decoded offline (OpenCV)
  press     Google News RSS, exact name in the headline, country or own domain checked (1 request / 3 s)
  people    public search-result snippets (DuckDuckGo HTML) for linkedin.com/in profiles naming the company and a target
            title (1 request / 12 s); stops for the run when the engine pushes back. No login, no CAPTCHA, nothing behind
            a login is read. OFF by default; switched on per run with --lanes
  wikidata  for companies the index marks notable or with stated employees: founding year, employees, revenue, chief
            executive and founders, only when the entity's official website is this company's domain (1 request / s)

Files in --dir: queue.jsonl (built once), site.jsonl, press.jsonl, people.jsonl, wikidata.jsonl (append-only, one
line per company and lane), status.json (counts only: the admin panel reads it), export/enrich.jsonl.gz (merged, for
the company-check workflow, which merges it into the website checks and the refined layer).

  python -m leads.enrich_server queue  --index suppliers.enc --dir D      (WEB_INDEX_KEY in the environment)
  python -m leads.enrich_server run    --dir D [--workers 16] [--lanes site,press,wikidata] [--only sample] [--minutes M]
  python -m leads.enrich_server sample --dir D --manufacturers 200 --traders 100
  python -m leads.enrich_server status|export|metrics --dir D
"""
import base64
import gzip
import json
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.robotparser import RobotFileParser

from . import company_check as cc
from . import company_profile as cp
from .common import log

SITE_PAGES = 10
PRODUCER_NAME = re.compile(r"\b(farms?|growers?|co-?op(erative)?s?|cooperativa|coop[ée]rative|plantations?|estates?|mills?|factory|factories|"
                           r"manufactur\w*|fabrica|fábrica|fabrik|industries|industrial|industria|ind[uú]stria|producers?|productores|refinery|"
                           r"smelter|foundry|works|brewery|dairy|poultry|agro|agri\w*|fertili[sz]er|cement|steel|textiles?|spinning|weaving|"
                           r"packers?|processing|pharma\w*|chemicals?|plastics?|工厂|制造|农场|合作社|实业|工业)\b", re.I)
TRADER_NAME = re.compile(r"\b(trading|traders?|import\w*|export\w*|distribut\w*|wholesal\w*|merchants?|commodities|comercial|comercializadora|"
                         r"negoce|handel|贸易|进出口)\b", re.I)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# ---------------------------------------------------------------- queue
def read_index(path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    b = Path(path).read_bytes()
    key = base64.b64decode(os.environ["WEB_INDEX_KEY"])
    return json.loads(gzip.decompress(AESGCM(key).decrypt(b[:12], b[12:], None)))


def role_tier(x):
    """0 producer, 1 goods supplier (role to be read from the site), 2 trader / distributor / exporter, 3 other."""
    ty, name = (x.get("ty") or "").lower(), x.get("n") or ""
    if re.search(r"manufacturer|producer", ty) or (PRODUCER_NAME.search(name) and not TRADER_NAME.search(name) and "works/services" not in ty):
        return 0
    if ty.startswith("trader") or x.get("td") or ty == "exporter" or TRADER_NAME.search(name):
        return 2
    if ty.startswith("goods supplier"):
        return 1
    return 3


def evidence(x):
    """Evidence points: customs shipments, contract wins, official export / registry records, notable, quality."""
    e = 0
    e += 3 if x.get("sh") else 0
    e += 2 if (x.get("w") or 0) > 0 else 0
    e += 2 if re.search(r"official|registered|customs|Wikidata", x.get("x") or "") else 0
    e += 1 if x.get("nt") else 0
    e += 1 if x.get("tr") in ("1", "2") else 0
    return e


def size_bucket(x):
    try:
        e = int(float(x.get("em") or 0))
    except ValueError:
        e = 0
    if e >= 1000 or x.get("nt"):
        return "large"
    if e >= 50:
        return "mid"
    if (x.get("w") or 0) >= 3 or (x.get("sh") or 0) >= 5:
        return "mid"  # repeat contract winners and regular shippers are established firms, rarely the biggest
    return "small/unknown"


def build_queue(rows):
    """Ordered [{key, name, country, website, tier, ev, size, sector, em, notable, sanctions_risk}]."""
    from .universe import SANCTIONS_COMPREHENSIVE, SANCTIONS_SECTORAL
    groups = defaultdict(list)
    for x in rows:
        if not x.get("n") or not x.get("c"):
            continue
        has_web = bool((x.get("web") or "").strip())
        t = role_tier(x)
        it = {"key": f"{x['n']}|{x['c']}", "name": x["n"], "country": x["c"], "website": (x.get("web") or "").strip(), "tier": t,
              "ev": evidence(x), "size": size_bucket(x), "sector": x.get("s", ""), "em": x.get("em", ""), "notable": bool(x.get("nt")),
              "sanctions_risk": "comprehensive" if x["c"] in SANCTIONS_COMPREHENSIVE else "sectoral" if x["c"] in SANCTIONS_SECTORAL else ""}
        # records without a website and without evidence go last; without a website but with evidence, after the sites
        band = 0 if has_web else 1 if it["ev"] >= 2 else 2
        groups[(band, t)].append(it)
    out, seen = [], set()
    for band in (0, 1, 2):
        for t in (0, 1, 2, 3):
            g = groups.get((band, t), [])
            # inside a tier: evidence first, then interleave size buckets so mid-size firms come as early as large ones
            by = defaultdict(list)
            for it in sorted(g, key=lambda i: (-i["ev"], i["name"])):
                by[it["size"]].append(it)
            order = ["mid", "large", "small/unknown"]
            idx = {k: 0 for k in order}
            while any(idx[k] < len(by[k]) for k in order):
                for k in order:
                    # small/unknown is most of the index: two of them per mid and large, so the mid band is not drowned
                    for _ in range(2 if k == "small/unknown" else 1):
                        if idx[k] < len(by[k]):
                            it = by[k][idx[k]]; idx[k] += 1
                            if it["key"] not in seen:
                                seen.add(it["key"]); out.append(it)
    return out


# ---------------------------------------------------------------- lanes
class Rate:
    def __init__(self, per_s):
        self.gap, self.next, self.lock = 1.0 / per_s, 0.0, threading.Lock()

    def wait(self):
        with self.lock:
            t = time.time()
            if t < self.next:
                time.sleep(self.next - t)
            self.next = max(t, self.next) + self.gap


def _session():
    s = cc._session()
    return s


def decode_wechat_qr(s, site_url, urls):
    """Fetch WeChat QR images on the company's own site (robots.txt respected, under 400 KB) and decode them offline."""
    out = []
    host = cc.site_domain(site_url)
    rp = RobotFileParser()
    try:
        r = s.get(f"{urlsplit(site_url).scheme}://{urlsplit(site_url).netloc}/robots.txt", timeout=10)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except Exception:  # noqa: BLE001
        rp.parse([])
    for u in urls[:2]:
        h = cc.site_domain(u)
        if not (h == host or h.endswith("." + cc.core_of(host) + "." + host.split(".")[-1]) or cc.core_of(h) == cc.core_of(host)):
            continue  # an image on another host is not fetched (CDN images stay as a link)
        if not rp.can_fetch(cc.UA, u):
            continue
        try:
            time.sleep(0.6)
            r = s.get(u, timeout=10, stream=True)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                b = r.raw.read(400_000, decode_content=True)
                r.close()
                txt = cp.decode_qr(b)
                if txt and txt not in out:
                    out.append(txt)
        except Exception:  # noqa: BLE001
            continue
    return out


def site_lane(it):
    """One company: its own site read and analysed (company_check + company_profile)."""
    t0 = time.time()
    stamp = now()
    base = {"key": it["key"], "supplier": it["name"], "country": it["country"], "website": it["website"], "checked": stamp[:10], "checked_at": stamp,
            "reason": f"server enrichment (tier {it['tier']})", "version": cc.VERSION, "record_sector": it.get("sector", ""), "tier": it["tier"],
            "sanctions_risk": it.get("sanctions_risk", ""), "source": "server-enrich"}
    if not it["website"]:
        return {**base, "verdict": "no website on record", "gaps": ["no website on record"], "content_hash": "", "secs": 0}
    pages, why = cc.fetch_site(it["website"], max_pages=SITE_PAGES)
    if not pages:
        return {**base, "verdict": why.split(" (")[0], "detail": why, "gaps": [why], "content_hash": "", "secs": round(time.time() - t0, 1)}
    import hashlib
    h = hashlib.sha1("".join(cc.text_of(p)[:20000] for _, p in pages).encode("utf-8", "ignore")).hexdigest()[:16]
    res = cc.analyse(it["name"], it.get("sector", ""), pages, it["country"])
    wx = res.get("wechat") or {}
    if wx.get("qr_images"):
        wx["decoded"] = decode_wechat_qr(_session(), pages[0][0], wx["qr_images"])
    return {**base, **res, "website": pages[0][0], "pages": [u for u, _ in pages][:SITE_PAGES], "content_hash": h, "secs": round(time.time() - t0, 1)}


GN = "https://news.google.com/rss/search"


def press_lane(s, it, site):
    names = [cp.press_name(it["name"])]
    if not names[0]:
        return {"key": it["key"], "checked_at": now(), "press": [], "skipped": "name too short or generic"}
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=it["country"])
        cn = [n for n in (getattr(c, "common_name", None), getattr(c, "name", None), getattr(c, "official_name", None)) if n] if c else []
    except Exception:  # noqa: BLE001
        cn = []
    r = s.get(GN, params={"q": f'"{names[0]}"', "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=15)
    if r.status_code != 200:
        return {"key": it["key"], "checked_at": now(), "error": f"HTTP {r.status_code}"}
    notable = bool(it.get("notable") or it.get("em") or it.get("size") == "large")
    arts = cp.press_filter(cp.parse_rss(r.text), it["name"], cn, (site or {}).get("domain", ""), notable)
    return {"key": it["key"], "checked_at": now(), "press": arts, "query": names[0]}


DDG = "https://html.duckduckgo.com/html/"
PEOPLE_Q = '(CEO OR "managing director" OR founder OR owner OR "general manager" OR "export manager" OR "sales manager" OR "sales director" OR procurement OR "business development")'


def people_lane(s, it, site):
    n = cp.press_name(it["name"])
    if not n:
        return {"key": it["key"], "checked_at": now(), "people": [], "skipped": "name too short or generic"}
    r = s.post(DDG, data={"q": f'"{n}" site:linkedin.com/in {PEOPLE_Q}'}, timeout=15)
    if r.status_code != 200 or "result__a" not in r.text and "No results" not in r.text and "no-results" not in r.text:
        return {"key": it["key"], "checked_at": now(), "blocked": f"HTTP {r.status_code}" if r.status_code != 200 else "unexpected page"}
    return {"key": it["key"], "checked_at": now(), "people": cp.snippet_people(cp.parse_ddg(r.text), it["name"])}


WD = "https://www.wikidata.org/w/api.php"


def wikidata_lane(s, it, site, rate):
    dom = (site or {}).get("domain", "")
    if not dom:
        return {"key": it["key"], "checked_at": now(), "wikidata": None, "skipped": "no confirmed domain"}
    rate.wait()
    r = s.get(WD, params={"action": "wbsearchentities", "search": it["name"][:80], "language": "en", "type": "item", "limit": 3, "format": "json"}, timeout=20)
    ids = [h["id"] for h in r.json().get("search", [])] if r.status_code == 200 else []
    if not ids:
        return {"key": it["key"], "checked_at": now(), "wikidata": None}
    rate.wait()
    r = s.get(WD, params={"action": "wbgetentities", "ids": "|".join(ids), "props": "claims", "format": "json"}, timeout=20)
    ents = (r.json().get("entities") or {}) if r.status_code == 200 else {}
    for q in ids:
        f = cp.wikidata_facts(ents.get(q) or {}, dom)
        if f:
            people = []
            qs = (f.get("ceo_qids") or []) + (f.get("founder_qids") or [])
            if qs:
                rate.wait()
                r = s.get(WD, params={"action": "wbgetentities", "ids": "|".join(qs[:6]), "props": "labels", "languages": "en", "format": "json"}, timeout=20)
                lab = (r.json().get("entities") or {}) if r.status_code == 200 else {}
                for qq in qs[:6]:
                    nm = (((lab.get(qq) or {}).get("labels") or {}).get("en") or {}).get("value")
                    if nm:
                        title = "chief executive officer" if qq in (f.get("ceo_qids") or []) else "founder"
                        people.append({"name": nm, "title": title, "role": "chief executive" if title.startswith("chief") else "founder / owner",
                                       "source": f["source"], "basis": "Wikidata statement", "confidence": "wikidata"})
            f["people"] = people
            return {"key": it["key"], "checked_at": now(), "wikidata": f}
    return {"key": it["key"], "checked_at": now(), "wikidata": None}


# ---------------------------------------------------------------- run
def keys_in(p):
    out = {}
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                out[d["key"]] = d
    return out


def light(d):
    """What the lanes need from a site record (keeps memory small on the full run)."""
    return {k: d.get(k) for k in ("verdict", "name_match", "domain", "roles", "people", "tier")}


def run(d, workers=16, lanes=("site", "press", "wikidata"), only="", minutes=0, limit=0):
    d = Path(d)
    q = [json.loads(x) for x in open(d / "queue.jsonl", encoding="utf-8")]
    if only:
        keep = set((d / f"{only}.keys").read_text(encoding="utf-8").splitlines())
        q = [it for it in q if it["key"] in keep]
    if limit:
        q = q[:limit]
    files = {ln: d / f"{ln}.jsonl" for ln in ("site", "press", "people", "wikidata")}
    done = {ln: set(keys_in(files[ln])) if ln != "site" else set() for ln in files}
    sites = {k: light(v) for k, v in keys_in(files["site"]).items()}
    done["site"] = set(sites)
    by_key = {it["key"]: it for it in q}
    lock = threading.Lock()
    stop = threading.Event()
    deadline = time.time() + minutes * 60 if minutes else 0
    stats = Counter()
    t_start = time.time()
    recent = []  # completion times of the site lane (throughput)
    fh = {ln: open(files[ln], "a", encoding="utf-8") for ln in files}

    def write(ln, rec):
        with lock:
            fh[ln].write(json.dumps(rec, ensure_ascii=False) + "\n"); fh[ln].flush()
            done[ln].add(rec["key"])

    todo = iter([it for it in q if it["key"] not in done["site"]])

    def site_worker():
        while not stop.is_set():
            if deadline and time.time() > deadline:
                return
            with lock:
                it = next(todo, None)
            if it is None:
                return
            try:
                rec = site_lane(it)
            except Exception as e:  # noqa: BLE001
                rec = {"key": it["key"], "supplier": it["name"], "country": it["country"], "verdict": "error", "detail": type(e).__name__, "checked_at": now()}
            write("site", rec)
            with lock:
                sites[rec["key"]] = light(rec)
                stats["site"] += 1
                recent.append(time.time())

    def ok(k):
        s_ = sites.get(k) or {}
        return s_.get("verdict") == "ok" and s_.get("name_match") in ("high", "partial")

    def slow_lane(ln, fn, per_s):
        s = _session()
        rate = Rate(per_s)
        blocked = 0
        while not stop.is_set():
            if deadline and time.time() > deadline:
                return
            with lock:
                cand = [k for k in list(sites) if k not in done[ln] and ok(k) and k in by_key]
            if ln == "wikidata":
                cand = [k for k in cand if by_key[k].get("notable") or by_key[k].get("em") or (sites[k].get("tier") == 0)]
            if ln == "people":  # only where the site itself named no role holder
                cand = [k for k in cand if not sites[k].get("people")]
            cand.sort(key=lambda k: (by_key[k]["tier"], -by_key[k]["ev"]))
            if not cand:
                if all(not t.is_alive() for t in site_threads):
                    return
                time.sleep(20); continue
            for k in cand[:50]:
                if stop.is_set() or (deadline and time.time() > deadline):
                    return
                try:
                    if ln == "wikidata":
                        rec = fn(s, by_key[k], sites[k], rate)
                    else:
                        rate.wait()
                        rec = fn(s, by_key[k], sites[k])
                except Exception as e:  # noqa: BLE001
                    rec = {"key": k, "checked_at": now(), "error": type(e).__name__}
                if rec.get("blocked"):
                    blocked += 1
                    stats[f"{ln}_blocked"] += 1
                    if blocked >= 3:
                        log.warning("%s lane: the source pushed back 3 times; lane stopped for this run", ln)
                        return
                    time.sleep(1800); continue
                blocked = 0
                write(ln, rec)
                stats[ln] += 1

    site_threads = [threading.Thread(target=site_worker, daemon=True) for _ in range(workers if "site" in lanes else 0)]
    others = []
    if "press" in lanes:
        others.append(threading.Thread(target=slow_lane, args=("press", press_lane, 1 / 3), daemon=True))
    if "people" in lanes:
        others.append(threading.Thread(target=slow_lane, args=("people", people_lane, 1 / 12), daemon=True))
    if "wikidata" in lanes:
        others.append(threading.Thread(target=slow_lane, args=("wikidata", wikidata_lane, 1.0), daemon=True))
    for t in site_threads + others:
        t.start()
    last_status, last_export = 0, time.time()
    try:
        while any(t.is_alive() for t in site_threads + others):
            time.sleep(5)
            if time.time() - last_status > 60:
                last_status = time.time()
                write_status(d, q, sites, done, stats, t_start, recent, lanes, state="running")
            if time.time() - last_export > 2 * 3600:  # the hourly company-check workflow picks up the newest export
                last_export = time.time()
                with lock:
                    for f in fh.values():
                        f.flush()
                export(d)
    except KeyboardInterrupt:
        stop.set()
    for f in fh.values():
        f.close()
    write_status(d, q, sites, done, stats, t_start, recent, lanes, state="done" if len(done["site"] & set(by_key)) >= len(q) else "paused")
    export(d)
    return stats


def write_status(d, q, sites, done, stats, t_start, recent, lanes, state):
    """status.json: counts only (no names, no contacts), for the admin panel's Server and tasks view."""
    total = len(q)
    keys = {it["key"] for it in q}
    by_tier = defaultdict(lambda: [0, 0])
    for it in q:
        by_tier[it["tier"]][1] += 1
        if it["key"] in sites:
            by_tier[it["tier"]][0] += 1
    n_done = sum(1 for k in sites if k in keys)
    hour = [t for t in recent if t > time.time() - 3600]
    rate = len(hour) if time.time() - t_start >= 3600 else round(len(recent) / max(1e-6, (time.time() - t_start) / 3600))
    verdicts = Counter(v.get("verdict") for k, v in sites.items() if k in keys)
    st = {"v": 1, "at": now(), "state": state, "lanes": list(lanes), "queue": total, "done": n_done, "remaining": total - n_done,
          "per_hour": rate, "eta_hours": round((total - n_done) / rate, 1) if rate else None,
          "by_tier": {["producer", "goods supplier", "trader", "other"][t]: {"done": a, "total": b} for t, (a, b) in sorted(by_tier.items())},
          "verdicts": dict(verdicts.most_common(8)), "lane_done": {ln: len(done[ln]) for ln in done}, "blocked": {k: v for k, v in stats.items() if k.endswith("_blocked")},
          "fill": fill_rates(d) if state != "running" or int(time.time()) % 600 < 60 else None}
    if st["fill"] is None:
        try:
            st["fill"] = json.loads((d / "status.json").read_text()).get("fill")
        except (OSError, ValueError):
            pass
    tmp = d / "status.json.tmp"
    tmp.write_text(json.dumps(st, separators=(",", ":")), encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(d / "status.json")


FIELDS = ["emails", "phones", "linkedin", "whatsapp_links", "wechat", "wechat_qr", "people_site", "people_linkedin", "founded", "employees",
          "revenue", "size", "capacity", "summary", "roles", "certificates", "press", "people_search", "wikidata"]


def has(rec, f):
    p = rec.get("profile") or {}
    wx = rec.get("wechat") or {}
    return {"emails": bool(rec.get("emails")), "phones": bool(rec.get("phones")), "linkedin": bool(rec.get("linkedin")),
            "whatsapp_links": bool(rec.get("whatsapp_links")), "wechat": bool(wx.get("ids") or wx.get("links") or wx.get("decoded")),
            "wechat_qr": bool(wx.get("qr_images")), "people_site": any(x.get("confidence", "own site") == "own site" for x in rec.get("people") or []),
            "people_linkedin": any(x.get("linkedin") for x in rec.get("people") or []), "founded": bool(p.get("founded")),
            "employees": bool(p.get("employees")), "revenue": bool(p.get("revenue")), "size": (p.get("size") or {}).get("band", "not stated") != "not stated",
            "capacity": bool(p.get("capacity") or p.get("plant_area")), "summary": bool(rec.get("summary")), "roles": bool(rec.get("roles")),
            "certificates": bool(rec.get("certificates")), "press": bool(rec.get("press")),
            "people_search": any(x.get("confidence") == "search snippet" for x in rec.get("people") or []), "wikidata": bool(rec.get("wikidata"))}[f]


def merged(d):
    """site records joined with the press, people and Wikidata lanes (streamed: one site record in memory at a time)."""
    d = Path(d)
    press, ppl, wd = keys_in(d / "press.jsonl"), keys_in(d / "people.jsonl"), keys_in(d / "wikidata.jsonl")
    seen = set()
    p = d / "site.jsonl"
    if not p.exists():
        return
    # one line per key (the run skips keys already read); a re-read of the same key keeps the first line here
    for line in open(p, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r["key"] in seen:
            continue
        seen.add(r["key"])
        r.pop("pages", None)
        extra = []
        if r["key"] in press and press[r["key"]].get("press"):
            r["press"] = press[r["key"]]["press"]; extra.append(press[r["key"]]["checked_at"])
        if r["key"] in ppl and ppl[r["key"]].get("people"):
            r["people"] = (r.get("people") or []) + [x for x in ppl[r["key"]]["people"] if x["name"] not in {y["name"] for y in r.get("people") or []}]
            extra.append(ppl[r["key"]]["checked_at"])
        w = (wd.get(r["key"]) or {}).get("wikidata")
        if w:
            r["wikidata"] = {k: v for k, v in w.items() if k != "people"}
            r["people"] = (r.get("people") or []) + [x for x in w.get("people", []) if x["name"] not in {y["name"] for y in r.get("people") or []}]
            prof = r.setdefault("profile", {})
            if w.get("founded") and not prof.get("founded"):
                prof["founded"] = {"value": w["founded"], "phrase": "Wikidata inception", "source": w["source"], "basis": "Wikidata (official website matches)"}
                prof["years_in_business"] = cp.THIS_YEAR - w["founded"]
            if w.get("employees") and not prof.get("employees"):
                prof["employees"] = {"value": w["employees"], "phrase": "Wikidata number of employees", "source": w["source"], "basis": "Wikidata (official website matches)"}
            prof["size"] = cp.size_band(prof)
            extra.append(wd[r["key"]]["checked_at"])
        r["enriched_at"] = max([r.get("checked_at", "")] + extra)
        yield r


def fill_rates(d):
    n, c, tiers = 0, Counter(), Counter()
    for r in merged(d):
        if r.get("verdict") != "ok":
            continue
        n += 1
        tiers[r.get("tier")] += 1
        for f in FIELDS:
            c[f] += has(r, f)
    return {"read_ok": n, **{f: round(100 * c[f] / n, 1) if n else 0 for f in FIELDS}}


def export(d):
    d = Path(d)
    (d / "export").mkdir(exist_ok=True)
    tmp = d / "export" / "enrich.jsonl.gz.tmp"
    n = 0
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for r in merged(d):
            if r.get("verdict") in ("no website on record",):
                continue
            f.write(json.dumps(r, ensure_ascii=False) + "\n"); n += 1
    tmp.replace(d / "export" / "enrich.jsonl.gz")
    log.info("export: %d records", n)
    return n


def sample(d, manufacturers=200, traders=100):
    """A measurement sample from the head of the queue: producers (tier 0, then goods suppliers the site may show as
    makers) and traders, all with a website, mixed sizes."""
    q = [json.loads(x) for x in open(Path(d) / "queue.jsonl", encoding="utf-8")]
    web = [it for it in q if it["website"]]
    m = [it for it in web if it["tier"] == 0]
    # every 7th producer, so the sample is not only the head of the queue
    m = (m[::7] + [it for it in web if it["tier"] == 1][::50])[:manufacturers]
    t = [it for it in web if it["tier"] == 2][::5][:traders]
    keys = [it["key"] for it in m + t]
    (Path(d) / "sample.keys").write_text("\n".join(keys), encoding="utf-8")
    return {"manufacturers": len(m), "traders": len(t), "sizes": dict(Counter(it["size"] for it in m + t))}


def metrics(d, keys_file=None):
    """Fill rates per field for a set of keys, by tier; and a review file (private) of 30 records for hand checks."""
    d = Path(d)
    keep = set((d / keys_file).read_text(encoding="utf-8").splitlines()) if keys_file else None
    by = defaultdict(Counter)
    n = Counter()
    verdicts = Counter()
    secs = []
    rows = []
    for r in merged(d):
        if keep is not None and r["key"] not in keep:
            continue
        verdicts[r.get("verdict")] += 1
        if r.get("secs"):
            secs.append(r["secs"])
        if r.get("verdict") != "ok":
            continue
        t = "producers" if r.get("tier") in (0, 1) else "traders" if r.get("tier") == 2 else "other"
        n[t] += 1
        for f in FIELDS:
            by[t][f] += has(r, f)
        rows.append(r)
    out = {"verdicts": dict(verdicts), "read_ok": dict(n), "median_secs_per_company": sorted(secs)[len(secs) // 2] if secs else None,
           "fill_pct": {t: {f: round(100 * by[t][f] / n[t], 1) for f in FIELDS} for t in n}}
    # the review set (private, stays on the server): records that carry the fields to check by hand
    import random
    random.seed(7)
    pick = [r for r in rows if r.get("people") or r.get("whatsapp_links") or (r.get("wechat") or {}).get("ids") or r.get("press")]
    random.shuffle(pick)
    with open(d / "review.jsonl", "w", encoding="utf-8") as f:
        for r in pick[:30]:
            f.write(json.dumps({k: r.get(k) for k in ("key", "website", "domain", "name_match", "roles", "people", "whatsapp_links", "wechat", "press", "profile", "summary")}, ensure_ascii=False) + "\n")
    return out


def main(argv):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    a = argv
    opt = lambda k, dflt="": a[a.index(k) + 1] if k in a else dflt  # noqa: E731
    cmd, d = a[0], Path(opt("--dir", "/e"))
    if cmd == "queue":
        q = build_queue(read_index(opt("--index")))
        with open(d / "queue.jsonl.tmp", "w", encoding="utf-8") as f:
            for it in q:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        (d / "queue.jsonl.tmp").replace(d / "queue.jsonl")
        c = Counter((it["tier"], bool(it["website"])) for it in q)
        print(json.dumps({"queue": len(q), "by_tier_and_site": {f"tier{t}{'_web' if w else '_noweb'}": v for (t, w), v in sorted(c.items())},
                          "sizes": dict(Counter(it["size"] for it in q)), "sanctions_risk": dict(Counter(it["sanctions_risk"] for it in q))}))
    elif cmd == "sample":
        print(json.dumps(sample(d, int(opt("--manufacturers", "200")), int(opt("--traders", "100")))))
    elif cmd == "run":
        st = run(d, int(opt("--workers", "16")), tuple(opt("--lanes", "site,press,wikidata").split(",")), opt("--only"), int(opt("--minutes", "0")), int(opt("--limit", "0")))
        print(json.dumps(dict(st)))
    elif cmd == "metrics":
        print(json.dumps(metrics(d, opt("--keys") or None)))
    elif cmd == "export":
        print(export(d))
    elif cmd == "countries":  # counts only (the log is public): queue size by country, with a website, producers
        q = [json.loads(x) for x in open(d / "queue.jsonl", encoding="utf-8")]
        c, w, p = Counter(), Counter(), Counter()
        for it in q:
            c[it["country"]] += 1; w[it["country"]] += bool(it["website"]); p[it["country"]] += it["tier"] == 0
        print(json.dumps({"queue": len(q), "by_country": [[k, n, w[k], p[k]] for k, n in c.most_common(80)]}))
    elif cmd == "status":
        print((d / "status.json").read_text() if (d / "status.json").exists() else "{}")


if __name__ == "__main__":
    main(sys.argv[1:])
