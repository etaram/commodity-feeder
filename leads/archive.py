"""Closed tenders leave the database unless we took part in them.

A notice whose deadline has passed and that is not in our own work (the Pipeline, Pursuits or Deal Records tabs of the
engine sheet) leaves tenders_all.csv. Nothing is destroyed: it moves to data/leads/archive/tenders_closed.csv.gz
(one line per notice, with the date it was archived), so award analysis and a rollback can still read it.
Planned notices (no deadline yet) and notices we worked on always stay.

Safety: if our own work cannot be read (no credentials, sheet error), nothing is archived in that run.
Rollback: ARCHIVE_CLOSED=off keeps every notice in tenders_all.csv."""
import csv
import gzip
import io
import os
from datetime import date

from .common import LEADS, log

ARCHIVE = LEADS / "archive" / "tenders_closed.csv.gz"
# where our participation lives: (tab range, column holding the opportunity / tender id)
OURS = [("'Pipeline'!A2:A5000", 0), ("'Pursuits'!A2:A5000", 0), ("'Deal Records'!B2:B20000", 0)]


def our_ids():
    """Tender ids we worked on, or None when they cannot be read (then nothing is archived)."""
    try:
        from .push import LEADS_SHEET, Sheets
        s = Sheets()
        ids = set()
        for rng, col in OURS:
            for r in s.values(LEADS_SHEET, rng) or []:
                if len(r) > col and str(r[col]).strip():
                    ids.add(str(r[col]).strip())
        return ids
    except (Exception, SystemExit) as e:  # noqa: BLE001
        log.info("archive: our work not readable (%s): nothing archived this run", str(e)[:80])
        return None


def is_closed(r, today):
    """Deadline passed and not a planned notice (pure)."""
    if (r.get("stage") or "tender") == "planned":
        return False
    d = r.get("days_left")
    if isinstance(d, (int, float)):
        return d < 0
    dl = str(r.get("deadline") or "")[:10]
    return bool(dl) and dl < today.isoformat()


def split(tenders, ours, today):
    """(kept, archived): closed notices we did not take part in are archived (pure)."""
    keep, gone = [], []
    for r in tenders:
        (gone if is_closed(r, today) and str(r.get("id", "")).strip() not in ours else keep).append(r)
    return keep, gone


def archive(tenders, cols):
    """Returns the tenders to keep in tenders_all.csv; appends the rest to the archive."""
    if os.environ.get("ARCHIVE_CLOSED", "on") == "off":
        return tenders
    ours = our_ids()
    if ours is None:
        return tenders
    today = date.today()
    keep, gone = split(tenders, ours, today)
    if not gone:
        return tenders
    old = {}
    if ARCHIVE.exists():
        with gzip.open(ARCHIVE, "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                old[r.get("id", "")] = r
    for r in gone:
        old[str(r.get("id", ""))] = {**{c: r.get(c, "") for c in cols}, "archived": today.isoformat()}
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(cols) + ["archived"], extrasaction="ignore")
    w.writeheader(); w.writerows(old.values())
    with gzip.open(ARCHIVE, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write(buf.getvalue())
    kept_ours = sum(1 for r in keep if is_closed(r, today))
    log.info("archive: %d closed notices moved to the archive (%d there in total); %d closed ones kept because we worked on them",
             len(gone), len(old), kept_ours)
    return keep
