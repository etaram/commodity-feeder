import csv
import datetime as dt
import json
import logging
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LEADS = DATA / "leads"
PARTIAL = LEADS / "partial"
log = logging.getLogger("leads")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class _Session(requests.Session):
    """requests session that falls back to the regional relay when a site refuses the runner's address
    (HTTP 403 or 451, or no connection). Logged each time, so the registry can say which sources needed it."""
    relayed = 0

    def get(self, url, **kw):
        try:
            r = super().get(url, **kw)
            if r.status_code not in (403, 451):
                return r
            why = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            r, why = None, type(e).__name__
        if kw.get("params"):
            url = url + ("&" if "?" in url else "?") + requests.compat.urlencode(kw["params"], doseq=True)
        rr = relay_get(url, timeout=kw.get("timeout", 40) if isinstance(kw.get("timeout"), (int, float)) else 40)
        if rr is not None and rr.status_code < 400:
            _Session.relayed += 1
            log.info("relay used for %s (%s)", url[:70], why)
            return rr
        if r is not None:
            return r
        raise requests.ConnectionError(f"{why} and relay unavailable for {url[:70]}")


def session():
    s = _Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,he;q=0.8"})
    return s


_RELAY = {}


def relay_config():
    """RELAY_URL and RELAY_SECRET: from the environment, else the private Supplier Universe sheet, tab Config
    (the same store as WEB_INDEX_KEY). Empty when neither is available; callers then fetch directly."""
    import os
    if _RELAY:
        return _RELAY
    url, sec = os.environ.get("RELAY_URL", ""), os.environ.get("RELAY_SECRET", "")
    if not (url and sec):
        try:
            from .push import UNIVERSE_SHEET, Sheets
            cfg = {r[0]: r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B10") if len(r) > 1}
            url, sec = cfg.get("RELAY_URL", url), cfg.get("RELAY_SECRET", sec)
        except Exception as e:  # noqa: BLE001
            log.warning("relay config: %s", type(e).__name__)
    _RELAY.update({"url": url, "secret": sec})
    return _RELAY


class RelayResponse:
    def __init__(self, status, content, url, ctype):
        self.status_code, self.content, self.url, self.headers = status, content, url, {"content-type": ctype}
        self.ok = 200 <= status < 300

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} via relay for {self.url}")


def relay_get(url, timeout=40, accept=None):
    """GET through the regional relay (dealdesk/RUNNER_ORACLE.md, "relay" section): a Vercel function in Frankfurt
    that fetches the page from a European address. Returns a response-like object, or None when the relay is not
    configured or fails, so a collector can fall back to a direct request."""
    import base64
    c = relay_config()
    if not (c.get("url") and c.get("secret")):
        return None
    try:
        h = {"x-relay-secret": c["secret"]}
        if accept:
            h["x-relay-accept"] = accept
        r = requests.get(c["url"], params={"url": url}, headers=h, timeout=timeout)
        j = r.json()
        if not j.get("ok"):
            log.warning("relay %s: %s", url[:60], j.get("error")); return None
        return RelayResponse(int(j["status"]), base64.b64decode(j["body"]), j.get("url") or url, j.get("type") or "")
    except Exception as e:  # noqa: BLE001
        log.warning("relay %s: %s", url[:60], type(e).__name__); return None


def cffi_get(url, **kw):
    from curl_cffi import requests as cr
    return cr.get(url, impersonate="chrome", timeout=60, **kw)


def today():
    return dt.date.today()


def clean(s, n=None):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:n] if n else s


def master_rows():
    return list(csv.DictReader(open(DATA / "master_rows.csv", encoding="utf-8")))


def benchmarks():
    """row -> (label, price, unit, source_key, date). Feed price, else the manual price kept in the sheet."""
    out = {}
    names = {int(r["row"]): r["name"] for r in master_rows()}
    for r in csv.DictReader(open(DATA / "prices.csv", encoding="utf-8")):
        if r.get("price_usd"):
            out[int(r["row"])] = (names.get(int(r["row"]), r["name"]), float(r["price_usd"]), r["unit_usd"],
                                  r["source_key"], r["price_date"])
    man = ROOT / "tools" / "manual_sources.csv"
    if man.exists():
        for r in csv.DictReader(open(man, encoding="utf-8")):
            row = int(r["row"])
            if row not in out and r.get("price"):
                try:
                    out[row] = (names.get(row, r["product"]), float(r["price"]), r["unit"], r["family"], r.get("date", ""))
                except ValueError:
                    pass
    return out


def fmt_bench(b):
    name, price, unit, key, date = b
    name = re.sub(r"\s+-\s+.*(futures|settlement).*$", "", name)
    return f"{clean(name, 60)}: {price:,.4g} {unit} ({key}, {date})"


def save_partial(name, rows, meta=None):
    PARTIAL.mkdir(parents=True, exist_ok=True)
    (PARTIAL / f"{name}.json").write_text(json.dumps({"source": name, "rows": rows, "meta": meta or {},
                                                      "ran": dt.datetime.utcnow().isoformat(timespec="minutes")},
                                                     ensure_ascii=False))


def polite(sec=2.5):
    time.sleep(sec)


CACHE = LEADS / "cache"


def rolling(name, new_rows, max_age_days=120):
    """Merge freshly fetched rows into a per-source rolling cache (one JSON object per line) so each run only has
    to fetch the last few days. Drops notices whose deadline has passed or that are older than max_age_days."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name}.jsonl"
    rows = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line); rows[r["id"]] = r
    for r in new_rows:
        rows[r["id"]] = r
    t = str(today()); cut = str(today() - dt.timedelta(days=max_age_days))
    keep = [r for r in rows.values()
            if (r.get("deadline") or "9999") >= t and (r.get("published") or t) >= cut]
    keep.sort(key=lambda r: r["id"])
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in keep) + "\n", encoding="utf-8")
    return keep, (p.stat().st_size if p.exists() else 0)


def cache_empty(name):
    p = CACHE / f"{name}.jsonl"
    return not p.exists() or p.stat().st_size < 10


AWARDS = LEADS / "awards"
PRIVATE = DATA / "private"  # git-ignored; persisted between CI runs with actions/cache


def save_awards(source, rows, keep_days=370):
    """Award notices are stored once per publication day (awards/<source>/YYYY-MM-DD.json) so history files are
    written once and rarely touched again. Rows with the same id are merged."""
    d = AWARDS / source
    d.mkdir(parents=True, exist_ok=True)
    # Supplier contact details are kept out of the public repository (private cache, pushed to a private sheet).
    contacts = []
    for r in rows:
        for c in r.pop("contacts", None) or []:
            if c.get("name"):
                c["source"] = source; c["seen"] = r.get("published", ""); contacts.append(c)
    if contacts:
        PRIVATE.mkdir(parents=True, exist_ok=True)
        with open(PRIVATE / f"contacts_{source}.jsonl", "a", encoding="utf-8") as f:
            for c in contacts:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    by_day = {}
    for r in rows:
        day = (r.get("published") or str(today()))[:10]
        by_day.setdefault(day, []).append(r)
    for day, lst in by_day.items():
        p = d / f"{day}.json"
        cur = {x["id"]: x for x in json.loads(p.read_text())} if p.exists() else {}
        for x in lst:
            cur[x["id"]] = x
        p.write_text(json.dumps(list(cur.values()), ensure_ascii=False, separators=(",", ":")))
    cut = str(today() - dt.timedelta(days=keep_days))
    for p in d.glob("*.json"):
        if p.stem < cut:
            p.unlink()
    return len(rows)


def award_days(source):
    d = AWARDS / source
    return {p.stem for p in d.glob("*.json")} if d.exists() else set()


_BUNDLES = {}


def chain_session(url):
    """requests session that verifies TLS for hosts that omit their intermediate certificate: the missing
    intermediate is fetched via the certificate's AIA URL (cached on disk) and added to the trust bundle.
    Verification stays on."""
    import tempfile
    import time as _t
    from urllib.parse import urlsplit
    import certifi
    host = urlsplit(url).netloc
    s = session()
    if host not in _BUNDLES:
        pem = CACHE / "certs" / f"{host}.pem"
        cadata = pem.read_text() if pem.exists() else ""
        for attempt in range(3):
            if cadata:
                break
            try:
                from aia import AIASession
                cadata = AIASession().cadata_from_url(url)
                pem.parent.mkdir(parents=True, exist_ok=True); pem.write_text(cadata)
            except Exception as e:  # noqa: BLE001
                log.warning("AIA %s attempt %d: %s", host, attempt + 1, e); _t.sleep(5)
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        f.write(open(certifi.where()).read() + "\n" + cadata); f.close()
        _BUNDLES[host] = f.name
    s.verify = _BUNDLES[host]
    return s
