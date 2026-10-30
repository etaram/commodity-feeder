"""Uruguay: ARCE / Compras Estatales open OCDS feed (RSS of releases per month, then each release)."""
import concurrent.futures as cf
import datetime as dt
import re
from collections import Counter

from .common import CACHE, log, rolling, session, today
from .ocds import tender_row
from .ocds_fetch import releases_of

RSS = "https://www.comprasestatales.gub.uy/ocds/rss/{y}/{m:02d}"
REL = "https://www.comprasestatales.gub.uy/ocds/release/{}"


def _one(s, rid, t):
    try:
        r = s.get(REL.format(rid), timeout=60)
        if r.status_code != 200:
            return None
        j = r.json(); best = None
        for rel in (releases_of(j) or ([j] if isinstance(j, dict) and "tender" in j else [])):
            idc = re.search(r"-(\d+)$", rid)
            row = tender_row(rel, source="ARCE (Uruguay)", prefix="UY", country="URY", lang="es", access="National (foreign firms may bid)", today_s=str(t),
                             link=f"https://www.comprasestatales.gub.uy/consultas/detalle/id/{idc.group(1) if idc else ''}")
            if row:
                row["id"] = f"UY-{rid}"; best = row
        return best
    except Exception:  # noqa: BLE001
        return None


def fetch():
    s, t = session(), today()
    known = set()
    p = CACHE / "uruguay.jsonl"
    if p.exists():
        known = {line.split('"id": "', 1)[1].split('"', 1)[0] for line in p.read_text().splitlines() if '"id": "' in line}
    months = [(t.year, t.month)]
    prev = t.replace(day=1) - dt.timedelta(days=1)
    months.append((prev.year, prev.month))
    items, cats = [], Counter()
    for y, m in months:
        r = s.get(RSS.format(y=y, m=m), timeout=120)
        if r.status_code != 200:
            log.warning("UY rss %s", r.status_code); continue
        for it in re.findall(r"<item>(.*?)</item>", r.text, flags=re.S):
            g = re.search(r"<guid>(.*?)</guid>", it); c = re.search(r"<category>(.*?)</category>", it)
            if g:
                cats[c.group(1) if c else ""] += 1
                if (c.group(1) if c else "") != "award" and not g.group(1).startswith("adjudicacion"):
                    items.append(g.group(1))
    todo = [i for i in dict.fromkeys(items) if f"UY-{i}" not in known][:700]
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda i: _one(s, i, t), todo))
    new = [x for x in res if x]
    rows, _ = rolling("uruguay", new)
    log.info("Uruguay new %d, open %d (fetched %d of %d; categories %s)", len(new), len(rows), len(todo), len(items), dict(cats))
    return rows, {"new": len(new)}
