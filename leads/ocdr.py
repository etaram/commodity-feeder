"""OCP Data Registry (data.open-contracting.org): bulk OCDS downloads from ~150 publishers in ~50 countries (strong
in Latin America, Africa and Asia). For the Supplier Universe it reads the latest years of each publication and keeps
every award with a named supplier; supplier contact points go to the private contacts cache.
Work is spread over runs (time budget); past years are read once, the current year is re-read monthly."""
import datetime as dt
import gzip
import io
import json
import re
import time

from .common import PRIVATE, log, session, today
from .ocds import award_rows
from .regions import iso3, region

BASE = "https://data.open-contracting.org/en"
OUT = PRIVATE / "awards_ext"
STATE = PRIVATE / "ocdr_state.json"
PRIORITY = {"Sub-Saharan Africa": 0, "Latin America": 0, "South Asia": 1, "Southeast Asia": 1, "East Asia": 1,
            "Middle East & North Africa": 1}
MAX_BYTES = 700_000_000


def _publications(s):
    r = s.get(f"{BASE}/search/", timeout=120)
    ids = list(dict.fromkeys(re.findall(r"/en/publication/(\d+)", r.text)))
    pubs = []
    for pid in ids:
        try:
            p = s.get(f"{BASE}/publication/{pid}", timeout=60)
        except Exception:  # noqa: BLE001
            continue
        if p.status_code != 200:
            continue
        title = re.sub(r"\s+", " ", (re.search(r"<title>(.*?)</title>", p.text, re.S) or [None, ""])[1]).split("|")[0].strip()
        country = title.split(":")[0].strip()
        years = sorted({int(y) for y in re.findall(r"name=(\d{4})\.jsonl\.gz", p.text) if int(y) > 1900})
        pubs.append({"id": pid, "title": title[:150], "iso": iso3(country) or "", "years": years})
        time.sleep(0.3)
    return pubs


def _read(s, pid, year, iso, title, t_end):
    url = f"{BASE}/publication/{pid}/download?name={year}.jsonl.gz"
    r = s.get(url, stream=True, timeout=120)
    if r.status_code != 200 or int(r.headers.get("content-length") or 0) > MAX_BYTES:
        return None
    rows, contacts, n = [], [], 0
    src = f"OCDS registry: {title[:60]}"
    with gzip.GzipFile(fileobj=r.raw) as gz:
        for line in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            if time.time() > t_end:
                break
            n += 1
            if '"awards"' not in line:
                continue
            try:
                rel = json.loads(line)
            except ValueError:
                continue
            for a in award_rows(rel, source=src, prefix=f"OC{pid}", country=iso):
                wcs = [iso3(x) or x for x in (a.get("winner_country") or "").split(",") if x]
                a["winner_country"] = ",".join(wcs) or iso
                for c in a.pop("contacts", None) or []:
                    c["country"] = iso3(c.get("country") or "") or iso
                    c["source"] = src
                    if c.get("email") or c.get("phone") or c.get("legal_id") or c.get("address"):
                        contacts.append(c)
                a.pop("email", None); a.pop("link", None)
                rows.append(a)
    r.close()
    return rows, contacts, n


def fetch():
    s = session(); t_end = time.time() + 1500
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not state.get("pubs") or state.get("listed", "") < str(today() - dt.timedelta(days=30)):
        state["pubs"] = _publications(s); state["listed"] = str(today())
    done = state.setdefault("done", {})
    todo = []
    for p in state["pubs"]:
        if not p["iso"] or not p["years"]:
            continue
        for y in [y for y in p["years"] if y >= today().year - 2][-3:]:
            k = f"{p['id']}/{y}"
            stale = y >= today().year and done.get(k, "") < str(today() - dt.timedelta(days=30))
            if k not in done or stale:
                todo.append((PRIORITY.get(region(p["iso"]), 2), -y, p, y))
    todo.sort(key=lambda x: (x[0], x[1]))
    OUT.mkdir(parents=True, exist_ok=True)
    stats = {"files": 0, "awards": 0, "contacts": 0}
    for _, _, p, y in todo:
        if time.time() > t_end - 60:
            break
        try:
            res = _read(s, p["id"], y, p["iso"], p["title"], min(t_end, time.time() + 600))
        except Exception as e:  # noqa: BLE001
            log.warning("OCDR %s/%s: %s", p["id"], y, e); res = None
        done[f"{p['id']}/{y}"] = str(today())
        if not res:
            continue
        rows, contacts, n = res
        with open(OUT / f"ocdr_{p['id']}_{y}.jsonl", "w", encoding="utf-8") as f:
            for a in rows:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
        if contacts:
            with open(PRIVATE / "contacts_ocdr.jsonl", "a", encoding="utf-8") as f:
                for c in contacts:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
        stats["files"] += 1; stats["awards"] += len(rows); stats["contacts"] += len(contacts)
        log.info("OCDR %s %s %s: %d releases, %d awards, %d contacts", p["id"], p["iso"], y, n, len(rows), len(contacts))
    STATE.write_text(json.dumps(state))
    stats["pending"] = max(0, len(todo) - stats["files"])
    log.info("OCDR %s", stats)
    return [], stats
