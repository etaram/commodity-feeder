"""Check-now worker: answers "check the website" from the panel within about a minute instead of the next hourly run.

A small long-running process on the company server (service checknow in deploy/docker-compose.server.prod.yml).
Every POLL seconds it reads the 'Check queue' tab of the engine sheet (time, company, country, by, website, sector;
written by POST /api/panel/company-check), and for each new request runs leads.company_check.check_one (the same
polite reading of the company's own site as the hourly job), then APPENDS one row for that company to the
'Company checks' tab of the universe sheet in exactly the format push_sheet writes (company_check.sheet_row), with
column D holding the full time of the check, so GET /api/panel/company-check (order by D desc) shows it at once.
The whole tab is never rewritten here; the hourly job (which still reads the same queue) replaces it later with its
own row for that company.

Website: from the request when given, else from the private universe.csv when present on the server
(UNIVERSE_CSV), else the check discovers it by name. State (last row read) and every result (jsonl) live in
STATE_DIR on a server volume, never in the repository.

  python -m leads.check_now            run forever
  python -m leads.check_now --once     one pass (for a test)
"""
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import log

POLL = int(os.environ.get("CHECKNOW_POLL_S", "15"))
STATE_DIR = Path(os.environ.get("CHECKNOW_STATE", "/state"))
UNIVERSE_CSV = Path(os.environ.get("UNIVERSE_CSV", str(STATE_DIR / "universe.csv")))
MAX_AGE_MIN = 30          # an older request is left to the hourly job (the worker was down)
MAX_PER_PASS = 6          # at most this many companies per pass; the rest wait for the next pass
WORKERS = 3               # companies in parallel (inside one company the pages are read one after another)
SITE = re.compile(r"^https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::\d{2,5})?(?:/[^\s]*)?$")


def _ts(v):
    """ISO time of a queue row -> aware datetime, or None (pure)."""
    try:
        return datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_site(v):
    """A website from a request: http(s) URL with a dotted host, else "" (pure). A bare domain gets http://."""
    v = str(v or "").strip().split()[0] if str(v or "").strip() else ""
    if v and not re.match(r"^https?://", v, re.I) and re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/|$)", v):
        v = "http://" + v
    return v[:300] if SITE.match(v) else ""


def pick_new(rows, state, now):
    """New requests in the queue rows (A2:F, oldest first) since the last pass (pure).
    Returns ([(row_index, name, country, website, sector, requested_at)], new_state).
    state = {"rows": rows already seen, "last": ISO time of the newest seen}. On the first pass (no state) only
    requests from the last MAX_AGE_MIN minutes are taken. Requests older than MAX_AGE_MIN are skipped. If the tab
    became shorter (rows removed), rows newer than "last" are taken."""
    seen = int(state.get("rows", -1))
    last = _ts(state.get("last", "")) if state.get("last") else None
    if seen < 0 or seen > len(rows):
        start = 0
    else:
        start = seen
    cutoff = now - timedelta(minutes=MAX_AGE_MIN)
    out, newest, keys = [], last, set()
    for i in range(start, len(rows)):
        r = (list(rows[i]) + [""] * 6)[:6]
        t = _ts(r[0])
        if not t or not r[1].strip():
            continue
        if (seen < 0 or seen > len(rows)) and last and t <= last:
            continue
        newest = t if not newest or t > newest else newest
        if t < cutoff:
            continue
        name, country = r[1].strip()[:200], r[2].strip().upper()[:3]
        k = f"{name.lower()}|{country}"
        if k in keys:
            continue
        keys.add(k)
        out.append((i, name, country, clean_site(r[4]), r[5].strip()[:80], r[0].strip()))
    return out, {"rows": len(rows), "last": newest.isoformat() if newest else state.get("last", "")}


def item_for(req, universe):
    """(key, name, country, website, record_sector, reason) for company_check.check_one (pure).
    universe: {"name|CTY": (website, sector)} and {"name": [(country, website, sector)]} from load_universe."""
    _, name, country, site, sector, _ = req
    by_key, by_name = universe
    rec = by_key.get(f"{name}|{country}") or next((x[1:] for x in by_name.get(name.lower(), []) if not country or x[0] == country), None)
    w, sec = (rec or ("", ""))
    return (f"{name}|{country}", name, country, site or w or "", sector or sec or "", "asked in the panel (check now)")


def load_universe(path=UNIVERSE_CSV, _cache={}):
    """Website and sector per company from the private universe.csv, when the file is on the server; reread when it
    changes. Only the three fields are kept in memory."""
    try:
        m = path.stat().st_mtime
    except OSError:
        return {}, {}
    if _cache.get("m") == m:
        return _cache["u"]
    by_key, by_name = {}, {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            w = (r.get("website") or "").strip()
            if not w:
                em = (r.get("email") or "").split(";")[0].strip()
                if "@" in em and not re.search(r"@(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|qq|163|126)\.", em, re.I):
                    w = em.split("@")[1]
            v = (w, r.get("main_sector", "") or "")
            by_key[f"{r.get('supplier', '')}|{r.get('country', '')}"] = v
            by_name.setdefault((r.get("supplier") or "").strip().lower(), []).append((r.get("country", ""), *v))
    _cache.update(m=m, u=(by_key, by_name))
    log.info("check now: universe loaded, %d companies", len(by_key))
    return by_key, by_name


def row_for_sheet(res):
    """The 'Company checks' row for one result, with D = the full UTC time of the check (pure)."""
    from .company_check import sheet_row
    row = sheet_row(res)
    row[3] = res.get("checked_at") or res.get("checked", "")
    return row


# ---------------------------------------------------------------- state and sheets
def _load_state():
    try:
        return json.loads((STATE_DIR / "checknow.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(st):
    p = STATE_DIR / "checknow.json"
    p.write_text(json.dumps(st), encoding="utf-8")


def _prev_checks():
    out = {}
    p = STATE_DIR / "company_checks.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line); out[d["key"]] = d
            except (ValueError, KeyError):
                pass
    return out


class _Sheets:
    """The service-account client, renewed every 40 minutes (its token lives one hour)."""
    def __init__(self):
        self.c, self.t = None, 0.0

    def get(self):
        if not self.c or time.time() - self.t > 2400:
            from .push import Sheets
            self.c, self.t = Sheets(), time.time()
        return self.c


def append_check(sh, row):
    from urllib.parse import quote
    from .push import API, UNIVERSE_SHEET
    url = f"{API}/{UNIVERSE_SHEET}/values/{quote(chr(39) + 'Company checks' + chr(39) + '!A1')}:append"
    sh._req("POST", url, params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}, json={"values": [row]})


def one_pass(S, st):
    from .company_check import check_one
    from .push import LEADS_SHEET
    rows = S.get().values(LEADS_SHEET, "'Check queue'!A2:F5000")
    now = datetime.now(timezone.utc)
    new, st2 = pick_new(rows, st, now)
    if not new:
        return st2, 0
    new = new[-MAX_PER_PASS:]
    universe = load_universe()
    prev = _prev_checks()
    items = [item_for(r, universe) for r in new]

    def run(it):
        t0 = time.time()
        try:
            res = check_one(it, prev.get(it[0]))
        except Exception as e:  # noqa: BLE001
            res = {"key": it[0], "supplier": it[1], "country": it[2], "website": it[3], "verdict": "check failed",
                   "gaps": [f"check failed ({type(e).__name__})"], "reason": it[5], "record_sector": it[4], "content_hash": ""}
        res["checked_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        res["checked"] = res["checked_at"][:10]
        return it, res, time.time() - t0

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex, open(STATE_DIR / "company_checks.jsonl", "a", encoding="utf-8") as f:
        for it, res, secs in ex.map(run, items):
            try:
                append_check(S.get(), row_for_sheet(res))
                done += 1
            except Exception as e:  # noqa: BLE001
                log.warning("check now: row not written for %s (%s)", it[1][:60], str(e)[:120])
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            log.info("check now: %s (%s) -> %s, site %s, %.0fs", it[1][:60], it[2], res.get("verdict"), "given" if it[3] else "looked up", secs)
    return st2, done


def main(once=False):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    S, st = _Sheets(), _load_state()
    log.info("check now: polling the Check queue every %ds (state: %s rows seen)", POLL, st.get("rows", "none"))
    while True:
        t0 = time.time()
        try:
            st, n = one_pass(S, st)
            _save_state(st)
        except (Exception, SystemExit) as e:  # noqa: BLE001  network or quota: try again next pass
            log.warning("check now: pass failed (%s)", str(e)[:160])
            S.c = None
        if once:
            return st
        time.sleep(max(2, POLL - (time.time() - t0)))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    main(once="--once" in sys.argv[1:])
