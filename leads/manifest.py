"""Runtime manifest: for every tender source, what actually ran and what reached the product.
  fetched      rows the last run returned (source_status.rows)
  status       OK / DEGRADED / STALE / DOWN ... and when it last ran and last succeeded
  snapshot     rows in the per-source snapshot the merge reads (data/leads/partial/<source>.json)
  active       snapshot rows the merge admits (not stale, not skipped, deadline today or later or none)
  published    rows from this source in the open list the app reads (sheet/tenders_open.csv.gz)
  consumed     same file's sha256 and build time, so the app's read-back can be matched to it
Writes data/leads/manifest.json and manifest.csv. Counts only, no record content.
  python -m leads.manifest"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
from collections import Counter

from .common import LEADS, PARTIAL, PAUSED_SOURCES


def build():
    from .run import TENDER_SOURCES
    st = {}
    try:
        st = {s["source"]: s for s in json.loads((LEADS / "source_status.json").read_text(encoding="utf-8"))["sources"]}
    except Exception:  # noqa: BLE001
        pass
    t = str(dt.date.today())
    label_to_key, snap, active = {}, {}, {}
    for s in sorted(set(TENDER_SOURCES) | PAUSED_SOURCES):
        p = PARTIAL / f"{s}.json"
        rows = json.loads(p.read_text(encoding="utf-8")).get("rows", []) if p.exists() else []
        snap[s] = len(rows)
        active[s] = 0 if s in PAUSED_SOURCES else sum(
            1 for r in rows if not r.get("stale") and not r.get("skip") and ((r.get("deadline") or "9999") >= t))
        for r in rows:
            if r.get("source"):
                label_to_key.setdefault(r["source"], s)
    f = LEADS / "sheet" / "tenders_open.csv.gz"
    pub, sha, built = Counter(), "", ""
    if f.exists():
        raw = f.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        built = dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes") + "Z"
        for r in csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8"))):
            pub[label_to_key.get(r.get("source", ""), "other:" + (r.get("source") or "")[:40])] += 1
    out = []
    for s in sorted(set(TENDER_SOURCES) | PAUSED_SOURCES):
        e = st.get(s, {})
        out.append({"source": s, "enabled": s not in PAUSED_SOURCES, "status": e.get("status", "no run"),
                    "last_run_at": e.get("last_run_at", ""), "last_good_at": e.get("last_good_at", ""),
                    "fetched": e.get("rows", 0), "snapshot": snap[s], "active": active[s], "published": pub.get(s, 0),
                    "warning": (e.get("warning") or "")[:160]})
    unmatched = {k: v for k, v in pub.items() if k.startswith("other:")}
    m = {"generated": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes") + "Z", "open_file": "data/leads/sheet/tenders_open.csv.gz",
         "open_file_sha256": sha, "open_file_built": built, "published_total": sum(pub.values()),
         "published_unmatched_sources": unmatched, "sources": out}
    (LEADS / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(LEADS / "manifest.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    return m


if __name__ == "__main__":
    m = build()
    print(json.dumps({k: v for k, v in m.items() if k != "sources"}, indent=1))
    for s in m["sources"]:
        print(f'{s["source"]:20} {s["status"]:9} fetched {s["fetched"]:>6} snapshot {s["snapshot"]:>6} active {s["active"]:>6} published {s["published"]:>6}')
