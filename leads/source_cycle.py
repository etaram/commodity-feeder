"""Permanent source-expansion cycle: candidate sources are probed every week, their status is kept in the registry,
and a weekly report counts what the system holds per region.

  python -m leads.source_cycle probe [ID ...]   probe the candidates (all, or the given ids) -> candidates_wave1.csv + candidates_probe.json
  python -m leads.source_cycle report            data/registry/weekly_report.json (per-region counts, week-over-week change)
  python -m leads.source_cycle cycle             probe + report (weekly, from deploy/ops/schedule.tab via sources.yml)
  python -m leads.source_cycle sample ID|URL [method]   fetch one page and keep it SEALED (developer review, never in the log)
  python -m leads.source_cycle run MODULE        run one collector's fetch() and print counts only (developer check)

Probing is polite: one request per host, 1.5 s apart, a User-Agent that names Sinder and its site, robots.txt read
and recorded (a disallowed path is never fetched), methods tried in order http -> relay -> stealth (the stealth
browser and the relay only when the plain request is refused; no login, no captcha solving). Only status codes,
host names, sizes and the robots verdict are written to the public files and the log.

Sealed samples: data/probe/sources/sealed/<name>.bin is encrypted to data/registry/review_pubkey.pem (RSA-OAEP +
AES-GCM), so a page or a match sample can be reviewed by whoever holds the private key without being published."""
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from urllib import robotparser

from .common import DATA, LEADS, PARTIAL, PRIVATE, log

REG = DATA / "registry"
CANDIDATES = REG / "candidates_wave1.csv"
PROBE_JSON = REG / "candidates_probe.json"
REPORT = REG / "weekly_report.json"
HISTORY = REG / "weekly_history.json"
SEALED = DATA / "probe" / "sources" / "sealed"
PUBKEY = REG / "review_pubkey.pem"
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
BOT = "SinderSources"
PROBE_COLS = ["http_status", "method_used", "final_host", "bytes", "robots", "reachable", "status", "checked_at"]
LOGIN_RX = re.compile(r"type=[\"']password[\"']|/login|sign[ _-]?in|iniciar sesi|connexion", re.I)
CHALLENGE_RX = re.compile(r"Just a moment|cf-chl|challenge-platform|captcha|Access Denied|Request unsuccessful", re.I)


# ---------------------------------------------------------------- sealing (review without publishing)
def seal(data: bytes, pub=PUBKEY) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = serialization.load_pem_public_key(Path(pub).read_bytes())
    k, n = AESGCM.generate_key(256), os.urandom(12)
    ek = key.encrypt(k, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return b"SEAL1" + len(ek).to_bytes(2, "big") + ek + n + AESGCM(k).encrypt(n, data, None)


def unseal(blob: bytes, private_key_pem: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    assert blob[:5] == b"SEAL1"
    n_ek = int.from_bytes(blob[5:7], "big")
    ek, nonce, ct = blob[7:7 + n_ek], blob[7 + n_ek:19 + n_ek], blob[19 + n_ek:]
    key = serialization.load_pem_private_key(private_key_pem, None)
    k = key.decrypt(ek, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return AESGCM(k).decrypt(nonce, ct, None)


def save_sealed(name, data):
    if not PUBKEY.exists():
        return None
    SEALED.mkdir(parents=True, exist_ok=True)
    p = SEALED / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', name)[:80]}.bin"
    p.write_bytes(seal(data if isinstance(data, bytes) else str(data).encode("utf-8")))
    return p


# ---------------------------------------------------------------- probing
def _session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en;q=0.9,*;q=0.5"})
    return s


def robots_verdict(s, url, fetch=None):
    """'allowed' / 'disallowed' / 'no robots.txt' / 'unreadable' for our bot and this path."""
    parts = urlsplit(url)
    rurl = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        r = fetch(rurl) if fetch else s.get(rurl, timeout=20)
        code = getattr(r, "status_code", 0)
    except Exception:  # noqa: BLE001
        return "unreadable"
    if code in (404, 410):
        return "no robots.txt"
    if code != 200 or "<html" in (r.text[:500].lower()):
        return "no robots.txt" if code == 200 else "unreadable"
    return robots_allows(r.text, url)


def robots_allows(text, url):
    rp = robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return "allowed" if rp.can_fetch(BOT, url) else "disallowed"


def classify_page(code, body):
    """open / login / challenge / error from one response."""
    if code in (None, 0):
        return "unreachable"
    head = (body or "")[:20000]
    if CHALLENGE_RX.search(head) and (code in (403, 429, 503) or len(head) < 12000):
        return "challenge"
    if code >= 400:
        return "error"
    if LOGIN_RX.search(head) and len(re.sub(r"<[^>]+>", " ", head)) < 3000:
        return "login"
    return "open"


def _try_http(s, url):
    try:
        r = s.get(url, timeout=30, allow_redirects=True)
        return r.status_code, urlsplit(r.url).netloc, r.text, len(r.content)
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__, "", 0


def _try_relay(url):
    from .common import relay_get
    r = relay_get(url, timeout=40)
    if r is None:
        return 0, "relay unavailable", "", 0
    return r.status_code, urlsplit(r.url).netloc, r.text, len(r.content)


def _try_stealth(url):
    try:
        from .stealth import fetcher
        p = fetcher().fetch(url, headless=True, network_idle=True, timeout=60000)
        body = p.html_content or ""
        return int(p.status or 0), urlsplit(url).netloc, body, len(body)
    except Exception as e:  # noqa: BLE001
        return 0, "stealth " + type(e).__name__, "", 0


def probe_row(c, s, allow=("http", "relay", "stealth")):
    url = c.get("probe_url") or c["url"]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    robots = robots_verdict(s, url)
    res = {"id": c["id"], "url": url, "host": urlsplit(url).netloc, "robots": robots, "checked_at": now, "tries": []}
    if robots == "disallowed":
        res.update(http_status="", method_used="", final_host="", bytes=0, reachable="no", status="robots_disallow")
        return res, ""
    best, body = None, ""
    for m in allow:
        if m != "http" and best and best[4] == "open":
            break
        if m == "relay" and best and best[4] not in ("challenge", "error", "unreachable"):
            break
        if m == "stealth" and best and best[4] in ("open", "login"):
            break
        code, host, text, n = _try_http(s, url) if m == "http" else _try_relay(url) if m == "relay" else _try_stealth(url)
        st = classify_page(code, text)
        res["tries"].append({"method": m, "code": code, "host": host if code else "", "bytes": n, "page": st})
        if best is None or (st == "open" and best[4] != "open") or (best[4] in ("unreachable", "error", "challenge") and st in ("login",)):
            best, body = (m, code, host, n, st), text
        time.sleep(1.5)
    m, code, host, n, st = best
    res.update(http_status=code or "ERR", method_used=m if st in ("open", "login") else "", final_host=host if code else "",
               bytes=n, reachable="yes" if st in ("open", "login") else "no", status=st)
    return res, body


def load_candidates():
    return list(csv.DictReader(open(CANDIDATES, encoding="utf-8")))


def write_candidates(rows):
    base = [k for k in rows[0].keys() if k not in PROBE_COLS]
    cols = base + PROBE_COLS
    with open(CANDIDATES, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def probe(ids=(), keep_bodies=False):
    rows = load_candidates()
    prev = json.loads(PROBE_JSON.read_text()) if PROBE_JSON.exists() else {}
    s = _session()
    allow = tuple(x for x in os.environ.get("PROBE_METHODS", "http,relay,stealth").split(",") if x)
    for c in rows:
        if ids and c["id"] not in ids:
            continue
        res, body = probe_row(c, s, allow)
        old = prev.get(c["id"], {})
        res["first_seen"] = old.get("first_seen") or res["checked_at"]
        res["last_reachable"] = res["checked_at"] if res["reachable"] == "yes" else old.get("last_reachable", "")
        res["history"] = (old.get("history") or [])[-11:] + [f"{res['checked_at'][:10]} {res['status']} {res['http_status']}"]
        prev[c["id"]] = res
        for k in PROBE_COLS:
            c[k] = res.get(k, "")
        print(f"PROBE {c['id']} {res['host']} -> {res['status']} {res['http_status']} via {res['method_used'] or '-'} robots={res['robots']} "
              + " ".join(f"{t['method']}:{t['code']}/{t['page']}" for t in res["tries"]))
        if keep_bodies and body:
            save_sealed(f"probe_{c['id']}", body)
    REG.mkdir(parents=True, exist_ok=True)
    PROBE_JSON.write_text(json.dumps(prev, indent=1, ensure_ascii=False, sort_keys=True))
    write_candidates(rows)
    tally = defaultdict(int)
    for c in rows:
        tally[c.get("status") or "not probed"] += 1
    print("probe summary", dict(tally))
    return rows


# ---------------------------------------------------------------- weekly report
def _region(c):
    from .regions import region
    return region(c) if c else "unknown"


def tender_counts():
    """open notices and active sources per region from the per-source snapshots (data/leads/partial)."""
    notices, sources = defaultdict(int), defaultdict(set)
    t = str(dt.date.today())
    for p in PARTIAL.glob("*.json"):
        try:
            rows = json.loads(p.read_text(encoding="utf-8")).get("rows") or []
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            if (r.get("deadline") or "9999") < t:
                continue
            g = _region((r.get("country") or "")[:3])
            notices[g] += 1
            sources[g].add(p.stem)
    return notices, {k: len(v) for k, v in sources.items()}


def award_counts(days=365):
    """award rows with a named winner per region (buyer country), last `days` days: day files awards/<source>/*.json
    and bulk files awards/<source>/*.jsonl (OCDR)."""
    from .common import AWARDS
    cut = str(dt.date.today() - dt.timedelta(days=days))
    out = defaultdict(int)

    def add(a):
        if a.get("empty") or not (a.get("winners") or a.get("winner") or a.get("supplier")):
            return
        if (a.get("published") or "9999")[:10] < cut and a.get("published"):
            return
        c = (a.get("country") or (a.get("winner_country") or "").split(",")[0])[:3]
        out[_region(c)] += 1
    for p in AWARDS.glob("*/*.json"):
        if re.match(r"\d{4}-\d\d-\d\d$", p.stem) and p.stem < cut:
            continue
        try:
            for a in json.loads(p.read_text(encoding="utf-8")):
                add(a)
        except Exception:  # noqa: BLE001
            continue
    for p in AWARDS.glob("*/*.jsonl"):
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    add(json.loads(line))
                except ValueError:
                    continue
    return out


def supplier_counts():
    """suppliers with a verified website and with an e-mail whose domain has MX records, per region (private universe)."""
    web, mx, total = defaultdict(int), defaultdict(int), defaultdict(int)
    p = PRIVATE / "universe.csv"
    if not p.exists():
        return None
    csv.field_size_limit(10 ** 8)
    mxmap = {}
    try:
        from .mx_check import load_results
        mxmap = load_results()
    except Exception:  # noqa: BLE001
        pass
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            g = r.get("region") or _region(r.get("country"))
            total[g] += 1
            if r.get("website") and (r.get("website_basis") or r.get("website_source") in ("refined", "checked")):
                web[g] += 1
            em = r.get("email_mx") or (mxmap.get((r.get("email") or "").split(";")[0].split("@")[-1].strip().lower(), {}).get("verdict") if r.get("email") else "")
            if em == "mx_ok":
                mx[g] += 1
    return total, web, mx


def active_sources_total():
    st = {}
    for f in ("source_status.json", "source_status_suppliers.json"):
        try:
            for s in json.loads((LEADS / f).read_text()).get("sources", []):
                st[s["source"]] = s.get("status")
        except Exception:  # noqa: BLE001
            pass
    return sum(1 for v in st.values() if v == "OK"), len(st)


def report(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    notices, act = tender_counts()
    awards = award_counts()
    sup = supplier_counts()
    regions = sorted(set(notices) | set(awards) | (set(sup[0]) if sup else set()))
    per = {}
    for g in regions:
        per[g] = {"open_notices": notices.get(g, 0), "awards_with_winner_12m": awards.get(g, 0),
                  "suppliers": sup[0].get(g, 0) if sup else None, "suppliers_verified_website": sup[1].get(g, 0) if sup else None,
                  "suppliers_mx_ok_email": sup[2].get(g, 0) if sup else None, "active_sources": act.get(g, 0)}
    ok, known = active_sources_total()
    cand = load_candidates() if CANDIDATES.exists() else []
    ctally = defaultdict(int)
    for c in cand:
        ctally[c.get("status") or "not probed"] += 1
    hist = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    week = now.strftime("%G-W%V")
    prev = next((h for h in reversed(hist) if h["week"] != week), None)
    change = {}
    if prev:
        for g, v in per.items():
            pv = prev["regions"].get(g, {})
            change[g] = {k: (v[k] - (pv.get(k) or 0)) if isinstance(v[k], int) and isinstance(pv.get(k), int) else None for k in v}
    snap = {"week": week, "generated": now.strftime("%Y-%m-%dT%H:%MZ"), "regions": per}
    hist = [h for h in hist if h["week"] != week] + [snap]
    rep = {"generated": snap["generated"], "week": week, "previous_week": prev["week"] if prev else None,
           "regions": per, "change_vs_previous_week": change,
           "totals": {k: sum((v[k] or 0) for v in per.values()) for k in ("open_notices", "awards_with_winner_12m", "suppliers",
                                                                          "suppliers_verified_website", "suppliers_mx_ok_email")},
           "sources_ok": ok, "sources_tracked": known, "candidates": dict(ctally),
           "note": "counts only; suppliers come from the private universe (absent when the cache is missing: null)"}
    REG.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rep, indent=1, ensure_ascii=False))
    HISTORY.write_text(json.dumps(hist[-104:], indent=1, ensure_ascii=False))
    print("weekly report", json.dumps(rep["totals"]), "candidates", dict(ctally))
    return rep


# ---------------------------------------------------------------- developer helpers
def sample(targets, method="http"):
    """fetch each target (candidate id or URL) once and seal the body; the log shows host, status and size only."""
    s = _session()
    cands = {r["id"]: r for r in load_candidates()} if CANDIDATES.exists() else {}
    for i, target in enumerate(targets):
        c = cands.get(target)
        url = (c.get("probe_url") or c["url"]) if c else target
        code, host, text, n = _try_http(s, url) if method == "http" else _try_relay(url) if method == "relay" else _try_stealth(url)
        p = save_sealed(f"sample_{c['id'] if c else urlsplit(url).netloc}_{i}_{method}", text or "")
        print(f"SAMPLE {i} {urlsplit(url).netloc} {method} -> {code} {n} bytes, sealed {p.name if p else '-'}")
        time.sleep(1.5)


def run_module(name):
    import importlib
    m = importlib.import_module(f"leads.{name}")
    t0 = time.time()
    rows, meta = m.fetch()
    by = defaultdict(int)
    for r in rows:
        by[r.get("country", "")] += 1
    print(f"RUN {name}: {len(rows)} rows in {time.time() - t0:.0f}s; meta {json.dumps(meta)[:300]}; by country {dict(by)}")
    if rows:
        save_sealed(f"run_{name}", json.dumps(rows[:30], ensure_ascii=False, indent=1))


def main(argv=None):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    a = sys.argv[1:] if argv is None else argv
    cmd = a[0] if a else "cycle"
    if cmd == "probe":
        probe(set(a[1:]), keep_bodies=os.environ.get("PROBE_SEAL") == "1")
    elif cmd == "report":
        report()
    elif cmd == "cycle":
        probe()
        report()
    elif cmd == "sample":
        meth = next((x.split("=", 1)[1] for x in a[1:] if x.startswith("--method=")), "http")
        sample([x for x in a[1:] if not x.startswith("--method=")], meth)
    elif cmd == "run":
        for n in a[1:]:
            try:
                run_module(n)
            except Exception as e:  # noqa: BLE001
                print(f"RUN {n}: failed {type(e).__name__}")
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
