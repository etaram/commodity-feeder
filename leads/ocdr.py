"""OCP Data Registry (data.open-contracting.org): bulk OCDS downloads from ~150 publishers in ~50 countries (strong
in Latin America, Africa and Asia). For the Supplier Universe it reads the latest years of each publication and keeps
every award with a named supplier; supplier contact points go to the private contacts cache.
Work is spread over runs (time budget); past years are read once, the current year is re-read monthly.
A publisher/year is marked done only after a complete read (to the end of the file) and an atomic write of its output.
A failed download, a file over the size limit and a read cut by the time budget are recorded separately (failed /
too_large / partial) and stay retryable; a partial read never replaces an earlier complete file. Award lines that are
not valid JSON/OCDS are counted: a file with rejects and no award, or rejects above 1% of its award lines, is invalid
(not published, not done, retried); a file without any award line and without rejects is a valid empty result."""
import datetime as dt
import gzip
import io
import json
import os
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


FAILED_RETRY_DAYS = 1      # a failed publisher/year is tried again after this many days
TOO_LARGE_RETRY_DAYS = 30


def _read(s, pid, year, iso, title, t_end):
    """(rows, contacts, releases read, complete) or a failure string ('http 503', 'too large')."""
    url = f"{BASE}/publication/{pid}/download?name={year}.jsonl.gz"
    r = s.get(url, stream=True, timeout=120)
    if r.status_code != 200:
        r.close(); return f"http {r.status_code}"
    if int(r.headers.get("content-length") or 0) > MAX_BYTES:
        r.close(); return "too large"
    rows, contacts, n, complete, bad = [], [], 0, True, 0
    good_lines, other, bad_other = 0, 0, 0   # award lines parsed; lines without an award; of those, not a JSON object
    src = f"OCDS registry: {title[:60]}"
    with gzip.GzipFile(fileobj=r.raw) as gz:
        for line in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            if time.time() > t_end:
                complete = False
                break
            n += 1
            if '"awards"' not in line:
                # cheap integrity check for the lines not parsed (no award text): a JSON object line starts with { and
                # ends with }. Counted, not certified: a well-formed line here may still be invalid OCDS.
                other += 1
                st = line.strip()
                if st and not (st.startswith("{") and st.endswith("}")):
                    bad_other += 1
                continue
            try:
                rel = json.loads(line)
                if not isinstance(rel, dict) or not isinstance(rel.get("awards", []), list):
                    raise ValueError("not an OCDS release")
                got = award_rows(rel, source=src, prefix=f"OC{pid}", country=iso)
                good_lines += 1
            except Exception:  # noqa: BLE001  - a line that is not valid JSON / OCDS is counted, never read as 'no awards'
                bad += 1
                continue
            for a in got:
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
    return rows, contacts, n, complete, {"bad": bad, "good_lines": good_lines, "other": other, "bad_other": bad_other}


MAX_BAD_SHARE = 0.01   # rejected award lines above 1% of the award lines (or any reject with no award read): invalid


def _write_atomic(path, rows):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for a in rows:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _due(rec, days):
    return not rec or rec.get("at", "") <= str(today() - dt.timedelta(days=days))


def fetch():
    s = session(); t_end = time.time() + 1500
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not state.get("pubs") or state.get("listed", "") < str(today() - dt.timedelta(days=30)):
        state["pubs"] = _publications(s); state["listed"] = str(today())
    done = state.setdefault("done", {})
    failed = state.setdefault("failed", {})        # key -> {"at", "tries", "why"}; retried after FAILED_RETRY_DAYS
    partial = state.setdefault("partial", {})      # key -> {"at", "releases"}; cut by the time budget, retried next run
    too_large = state.setdefault("too_large", {})  # key -> {"at"}; retried after TOO_LARGE_RETRY_DAYS
    # recovery of the old behaviour (a key was marked done before checking the read): a done key without its output
    # file was never read, so it goes back to the work list (bounded by the normal per-run time budget)
    recovered = [k for k in list(done) if not (OUT / f"ocdr_{k.replace('/', '_')}.jsonl").exists()]
    for k in recovered:
        done.pop(k, None); failed.setdefault(k, {"at": "", "tries": 0, "why": "marked done without output (before fix)"})
    todo = []
    for p in state["pubs"]:
        if not p["iso"] or not p["years"]:
            continue
        for y in [y for y in p["years"] if y >= today().year - 2][-3:]:
            k = f"{p['id']}/{y}"
            stale = y >= today().year and done.get(k, "") < str(today() - dt.timedelta(days=30))
            if not (k not in done or stale):
                continue
            if k in too_large and not _due(too_large[k], TOO_LARGE_RETRY_DAYS):
                continue
            if k in failed and not _due(failed[k], FAILED_RETRY_DAYS):
                continue
            todo.append((PRIORITY.get(region(p["iso"]), 2), -y, p, y))
    todo.sort(key=lambda x: (x[0], x[1]))
    OUT.mkdir(parents=True, exist_ok=True)
    stats = {"files": 0, "awards": 0, "contacts": 0, "failed": 0, "invalid": 0, "rejected_lines": 0, "partial": 0, "too_large": 0, "recovered": len(recovered)}
    for _, _, p, y in todo:
        if time.time() > t_end - 60:
            break
        k = f"{p['id']}/{y}"
        try:
            res = _read(s, p["id"], y, p["iso"], p["title"], min(t_end, time.time() + 600))
        except Exception as e:  # noqa: BLE001
            log.warning("OCDR %s/%s: %s", p["id"], y, e); res = type(e).__name__
        if isinstance(res, str) or res is None:
            why = res or "no answer"
            if why == "too large":
                too_large[k] = {"at": str(today())}; stats["too_large"] += 1
            else:
                f = failed.get(k) or {"tries": 0}
                failed[k] = {"at": str(today()), "tries": int(f.get("tries") or 0) + 1, "why": why[:60]}; stats["failed"] += 1
            continue
        rows, contacts, n, complete, integ = res
        bad, bad_other = integ["bad"], integ["bad_other"]
        path = OUT / f"ocdr_{p['id']}_{y}.jsonl"
        # shares are of INPUT lines (row 129): rejected award lines against all award lines, and malformed other lines
        # against all other lines; output award rows are not the denominator (one release can carry many awards)
        if (bad and (not rows or bad > MAX_BAD_SHARE * (bad + integ["good_lines"]))) or \
                (bad_other and bad_other > MAX_BAD_SHARE * integ["other"]):
            # invalid content: not a valid empty result. Nothing replaced, not done, retried after the failure backoff
            f = failed.get(k) or {"tries": 0}
            failed[k] = {"at": str(today()), "tries": int(f.get("tries") or 0) + 1, "why": f"invalid: {bad} of {bad + integ['good_lines']} award lines rejected, {bad_other} of {integ['other']} other lines malformed"}
            stats["invalid"] += 1
            log.warning("OCDR %s %s %s: %d of %d award lines rejected, %d of %d other lines malformed: not published, retried later",
                        p["id"], p["iso"], y, bad, bad + integ["good_lines"], bad_other, integ["other"])
            continue
        if bad or bad_other:
            stats["rejected_lines"] += bad + bad_other
            # tolerated rejects stay visible in the state (never 'complete coverage'); cleared by a clean re-read
            state.setdefault("tolerated", {})[k] = {"at": str(today()), "releases": n, "rejected_lines": bad + bad_other}
        else:
            state.setdefault("tolerated", {}).pop(k, None)
        if not complete:
            partial[k] = {"at": str(today()), "releases": n}; stats["partial"] += 1
            if path.exists():               # keep the last complete file; the partial read is dropped
                log.info("OCDR %s %s %s: cut by the time budget after %d releases; earlier file kept", p["id"], p["iso"], y, n)
                continue
        _write_atomic(path, rows)
        if contacts:
            with open(PRIVATE / "contacts_ocdr.jsonl", "a", encoding="utf-8") as f:
                for c in contacts:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
        if complete:
            done[k] = str(today()); failed.pop(k, None); partial.pop(k, None); too_large.pop(k, None)
            stats["files"] += 1
        stats["awards"] += len(rows); stats["contacts"] += len(contacts)
        log.info("OCDR %s %s %s: %d releases, %d awards, %d contacts%s", p["id"], p["iso"], y, n, len(rows), len(contacts),
                 "" if complete else " (partial, retried next run)")
    tmp = STATE.with_name(STATE.name + ".tmp"); tmp.write_text(json.dumps(state)); os.replace(tmp, STATE)
    stats["pending"] = max(0, len(todo) - stats["files"])
    stats["tolerated_total"] = len(state.get("tolerated") or {}); stats["failed_total"] = len(failed); stats["partial_total"] = len(partial); stats["too_large_total"] = len(too_large)
    log.info("OCDR %s", stats)
    return [], stats
