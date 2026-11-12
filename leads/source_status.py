"""Per-source status of the tender collectors, written on every run to data/leads/source_status.json, so a failed
collector never reads as a success.

For each source: status, rows this run, rows of the last good run, last_good_at, last_run_at, error_class.
  OK            the run returned rows, at least half of the last good run
  DEGRADED      zero rows (the previous good snapshot is kept, never overwritten by an empty one), or fewer than half
                the rows of the last good run (the new data is kept, with a warning)
  STALE         the last good run is older than the source's expected cadence
  DOWN          the collector raised (network, parsing, anything else); the previous good snapshot is kept
  DENIED        the site refused us (HTTP 401 / 403); the previous good snapshot is kept
  RATE_LIMITED  the site throttled us (HTTP 429); the previous good snapshot is kept
error_class is the exception type and, when there is one, the HTTP status. Never the message: messages can carry
URLs with tokens or long pages.

The merge has its own guard (merge_guard): an empty merged list, or one that lost more than half its rows since the
last good merge, stops the merge with an error before any output file is written, unless the override is given
(python -m leads.run --merge --allow-shrink, or LEADS_ALLOW_SHRINK=1).

  python -m leads.source_status                  recompute staleness and print the sources that are not OK
  python -m leads.source_status --suppliers      the same for the supplier-side modules (source_status_suppliers.json)
  python -m leads.source_status --accept NAME    accept a source's current row count as the new good baseline

Modules that write files instead of returning rows (awards, grants, markets, importyeti and the supplier-side
modules in WORK) report the volume they wrote (from their meta); "nothing due" runs are OK, not DEGRADED.
"""
import datetime as dt
import json
import os
import re
import sys

from . import common

FILE = "source_status.json"
STATUSES = ("OK", "DEGRADED", "STALE", "DOWN", "DENIED", "RATE_LIMITED")
DROP = 0.5             # fewer than half the rows of the last good run is a warning
DEFAULT_CADENCE_H = 36  # heavy sources run twice a day (leads.yml): three missed runs
LIGHT_CADENCE_H = 8     # light sources run every two hours: four missed runs
# the "LIGHT" list of .github/workflows/leads.yml
LIGHT = {"ted", "fts", "sam", "canadabuys", "ungm", "undp", "ebrd", "aiib", "isdb", "afdb", "iadb", "simap", "gets", "etimad", "prozorro", "pncp", "secop",
         "contractsfinder", "austender", "oman", "qatar", "kenya", "rwanda", "uganda", "ghana", "malawi", "mozambique", "dubai", "philippines", "moldova", "uruguay", "malaysia"}
FAILED = ("DOWN", "DENIED", "RATE_LIMITED")
# Modules that write files (award day files, caches, CSVs) instead of returning rows: their real volume is in the meta
# they return. name -> (meta keys summed as the row count, test on meta meaning "nothing was due this run").
WORK = {
    "awards": (("notices",), lambda m: not m.get("days")),
    "grants": (("calls",), lambda m: False),
    "markets": (("refreshed",), lambda m: m.get("due") == 0),
    "importyeti": (("scanned",), lambda m: m.get("due") == 0),
    "latam_awards": (("brazil", "colombia"), lambda m: False),
    "prozorro_awards": (("awards",), lambda m: not m.get("candidates")),
    "ocdr": (("awards",), lambda m: not m.get("files") and not m.get("pending")),
    "ext_awards": (("worldbank", "usaspending"), lambda m: not m),
    "il_exemptions": (("kept",), lambda m: False),
    "wikidata_companies": (("companies",), lambda m: not m.get("countries")),
    "listed_companies": (("companies",), lambda m: not m.get("countries")),
    "commodity_producers": (("companies",), lambda m: m.get("note") == "fresh"),
    "web_contacts": (("profiles", "discovered"), lambda m: m.get("tried") == 0),
    "iadb_awards": (("awards",), lambda m: False),
    "gebiz_awards": (("awards",), lambda m: m.get("note") == "fresh"),
}
# supplier-side modules run in suppliers.yml, which commits its own status file (leads.yml owns source_status.json)
SUPPLIER_SIDE = {"latam_awards", "prozorro_awards", "ocdr", "ext_awards", "il_exemptions", "wikidata_companies", "listed_companies",
                 "commodity_producers", "web_contacts", "gebiz_awards"}
SUPPLIER_FILE = "source_status_suppliers.json"


def work_from_meta(name, meta):
    """(rows written, idle) for a file-writing module; (None, False) for a module that returns its rows."""
    if name not in WORK:
        return None, False
    keys, idle = WORK[name]
    meta = meta or {}
    n = 0
    for k in keys:
        v = meta.get(k)
        n += v if isinstance(v, int) else len(v) if isinstance(v, (list, dict)) else 0
    try:
        return n, bool(idle(meta)) and n == 0
    except Exception:  # noqa: BLE001
        return n, False


class MergeGuardError(RuntimeError):
    pass


def cadence_h(name):
    return LIGHT_CADENCE_H if name in LIGHT else DEFAULT_CADENCE_H


def _now(now=None):
    return now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _iso(t):
    return t.isoformat(timespec="minutes")


def group_of(name):
    return "suppliers" if name in SUPPLIER_SIDE else "tenders"


def _path(group="tenders"):
    return common.LEADS / (SUPPLIER_FILE if group == "suppliers" else FILE)


def load(group="tenders"):
    """{"sources": {name: entry}, "merge": {...}}; an unreadable or missing file is an empty state."""
    try:
        j = json.loads(_path(group).read_text(encoding="utf-8"))
        return {"sources": {s["source"]: s for s in j.get("sources", []) if s.get("source")}, "merge": j.get("merge") or {}}
    except Exception:  # noqa: BLE001
        return {"sources": {}, "merge": {}}


def save(state, now=None, group="tenders"):
    order = {s: i for i, s in enumerate(("DOWN", "DENIED", "RATE_LIMITED", "STALE", "DEGRADED", "OK"))}
    rows = sorted(state["sources"].values(), key=lambda s: (order.get(s.get("status"), 0), s["source"]))
    common.LEADS.mkdir(parents=True, exist_ok=True)
    _path(group).write_text(json.dumps({"generated": _iso(_now(now)) + "Z", "not_ok": sum(1 for s in rows if s.get("status") != "OK"),
                                   "sources": rows, "merge": state.get("merge") or {}}, indent=1), encoding="utf-8")


def classify_error(exc):
    """(status, error_class) for an exception. The class is the exception type plus the HTTP status when one is known."""
    code = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if not isinstance(code, int):
        m = re.search(r"\b(401|403|429)\b", str(exc)[:300])   # collectors that raise their own "HTTP 403" errors
        code = int(m.group(1)) if m else None
    name = re.sub(r"[^A-Za-z0-9_.]", "", type(exc).__name__)[:60] or "Exception"
    status = "RATE_LIMITED" if code == 429 else "DENIED" if code in (401, 403) else "DOWN"
    return status, (f"{name}:{code}" if code else name)


def _entry(state, name):
    """The stored entry, or one built from the snapshot already on disk (first run of this module)."""
    e = state["sources"].get(name)
    if e:
        return e
    e = {"source": name, "status": "OK", "rows": 0, "rows_last_good": 0, "last_good_at": "", "last_run_at": "", "error_class": "", "warning": "", "cadence_h": cadence_h(name)}
    try:
        j = json.loads((common.PARTIAL / f"{name}.json").read_text(encoding="utf-8"))
        if j.get("rows"):
            e.update(rows=len(j["rows"]), rows_last_good=len(j["rows"]), last_good_at=j.get("ran", ""))
    except Exception:  # noqa: BLE001
        pass
    state["sources"][name] = e
    return e


def _apply_stale(e, now):
    """STALE when the last good run is older than the cadence. A failure status of the last run is kept (it says more)."""
    e["cadence_h"] = e.get("cadence_h") or cadence_h(e["source"])
    age = None
    try:
        age = (now - dt.datetime.fromisoformat(e["last_good_at"])).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        pass
    e["age_h"] = None if age is None else round(age, 1)
    old = age is not None and age > e["cadence_h"]
    if old and e.get("status") in ("OK", "DEGRADED"):
        e["status"] = "STALE"
        e["warning"] = (f"last good run {e['age_h']} h ago (expected every {e['cadence_h']} h)" + ("; " + e["warning"] if e.get("warning") and "last good run" not in e["warning"] else ""))[:200]
    elif not old and e.get("status") == "STALE":
        e["status"] = "OK"
        e["warning"] = ""
    return e


def record_failure(name, exc, now=None):
    """The collector raised: the snapshot on disk is left as it is, and the source is DOWN / DENIED / RATE_LIMITED."""
    now = _now(now)
    g = group_of(name)
    state = load(g)
    e = _entry(state, name)
    status, cls = classify_error(exc)
    e.update(status=status, rows=0, last_run_at=_iso(now), error_class=cls, warning="collector failed; the previous snapshot is kept")
    _apply_stale(e, now)
    save(state, now, g)
    return e


def record_result(name, rows, meta=None, now=None, save_fn=None):
    """The collector returned. Decides whether the snapshot is replaced, writes the status, returns the entry.
    save_fn(name, rows, meta) writes the snapshot (leads.common.save_partial unless a test passes its own)."""
    now = _now(now)
    save_fn = save_fn or common.save_partial
    g = group_of(name)
    state = load(g)
    e = _entry(state, name)
    n, good = len(rows or []), int(e.get("rows_last_good") or 0)
    e.update(rows=n, last_run_at=_iso(now), error_class="", warning="")
    work, idle = work_from_meta(name, meta) if n == 0 else (None, False)
    if work:
        # a file-writing module: its volume is what it wrote (no row snapshot to keep or replace; volumes vary per run)
        e.update(status="OK", rows=work, rows_last_good=work, last_good_at=_iso(now), kind="files")
    elif idle:
        e.update(status="OK", rows=0, last_good_at=_iso(now), kind="files", warning="nothing due this run (caches are fresh)")
    elif work == 0:
        e.update(status="DEGRADED", error_class="zero_work", kind="files",
                 warning=("wrote nothing although work was due: " + ", ".join(f"{k} {v}" for k, v in (meta or {}).items() if isinstance(v, (int, str)))[:150]))
    elif n == 0:
        # never overwrite a good snapshot with an empty one; with no history there is nothing to keep, and it is still not OK
        e.update(status="DEGRADED", error_class="zero_rows",
                 warning=f"returned 0 rows; the previous snapshot ({good} rows) is kept" if good else "returned 0 rows and has no good run on record")
        if not good and not (common.PARTIAL / f"{name}.json").exists():
            save_fn(name, rows or [], meta)
    elif good and n < good * DROP:
        save_fn(name, rows, meta)
        e.update(status="DEGRADED", error_class="rows_dropped", warning=f"rows fell from {good} to {n}; the new data is kept. If this is real, accept it: python -m leads.source_status --accept {name}")
    else:
        save_fn(name, rows, meta)
        e.update(status="OK", rows_last_good=n, last_good_at=_iso(now))
    _apply_stale(e, now)
    save(state, now, g)
    if e["status"] != "OK":
        common.log.warning("source %s: %s (%s)", name, e["status"], e["warning"])
    return e


def refresh(names=(), now=None, group="tenders"):
    """Recomputes staleness for every known source (and the given names, so a source that never ran is listed)."""
    now = _now(now)
    state = load(group)
    for n in names:
        _entry(state, n)
    for e in state["sources"].values():
        if not e.get("last_good_at") and not e.get("last_run_at"):
            e.update(status="STALE", warning="no run on record")
        _apply_stale(e, now)
    save(state, now, group)
    return state


def accept(name, now=None):
    now = _now(now)
    g = group_of(name)
    state = load(g)
    e = state["sources"].get(name)
    if not e or not e.get("rows"):
        raise SystemExit(f"{name}: no rows on record to accept")
    e.update(status="OK", rows_last_good=e["rows"], last_good_at=e.get("last_run_at") or _iso(now), error_class="", warning="")
    _apply_stale(e, now)
    save(state, now, g)
    return e


def allow_shrink(flag=False):
    return bool(flag) or os.environ.get("LEADS_ALLOW_SHRINK", "") == "1"


def merge_guard(n_rows, allow=False, now=None):
    """Called by the merge before it writes anything. Raises MergeGuardError when the merged list is empty or lost
    more than half its rows since the last good merge, unless allow is set. Records the outcome either way."""
    now = _now(now)
    state = load()
    m = state.get("merge") or {}
    good = int(m.get("rows_last_good") or 0)
    problem = "the merged list is empty" if n_rows == 0 else f"the merged list fell from {good} to {n_rows} rows" if good and n_rows < good * DROP else ""
    if problem and not allow:
        m.update(status="DOWN" if n_rows == 0 else "DEGRADED", rows=n_rows, last_run_at=_iso(now), error_class="merge_empty" if n_rows == 0 else "merge_rows_dropped",
                 warning=problem + "; the previous output files are kept")
        state["merge"] = m
        save(state, now)
        raise MergeGuardError(problem + ". Nothing was written. To accept it: python -m leads.run --merge --allow-shrink (or LEADS_ALLOW_SHRINK=1)")
    m.update(status="OK", rows=n_rows, rows_last_good=n_rows, last_good_at=_iso(now), last_run_at=_iso(now), error_class="", warning=("accepted with the override: " + problem) if problem else "")
    state["merge"] = m
    save(state, now)
    return m


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--accept"] and len(argv) == 2:
        e = accept(argv[1])
        print(f"{e['source']}: baseline is now {e['rows_last_good']} rows")
        return 0
    group = "suppliers" if "--suppliers" in argv else "tenders"
    state = refresh(group=group)
    bad = [e for e in state["sources"].values() if e.get("status") != "OK"]
    for e in bad:
        print(f"SOURCE {e['status']:12} {e['source']:18} rows {e.get('rows', 0)} (last good {e.get('rows_last_good', 0)} at {e.get('last_good_at') or '-'}) {e.get('error_class', '')}")
    print(f"source status: {len(state['sources'])} sources, {len(bad)} not OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
