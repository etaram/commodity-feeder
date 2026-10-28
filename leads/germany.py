"""Germany: oeffentlichevergabe.de daily OCDS export of all published notices (national and EU-threshold).
Tender-stage releases are kept; awards are saved for the awards layer."""
import datetime as dt
import io
import json
import zipfile

from .common import PRIVATE, cache_empty, log, rolling, save_awards, session, today
from .ocds import award_rows, tender_row

URL = "https://www.oeffentlichevergabe.de/api/notice-exports"


def fetch():
    s, t = session(), today()
    days = 14 if cache_empty("germany") else 2
    new, awards, aw = [], 0, []
    for k in range(1, days + 1):
        d = t - dt.timedelta(days=k)
        r = s.get(URL, params={"pubDay": d.isoformat(), "format": "ocds.zip"}, timeout=180)
        if r.status_code != 200 or not r.content.startswith(b"PK"):
            log.warning("DE %s %s", d, r.status_code); continue
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for name in z.namelist():
            try:
                pkg = json.loads(z.read(name))
            except ValueError:
                continue
            for rel in pkg.get("releases", []):
                tags = rel.get("tag") or []
                if "award" in tags or "contract" in tags:
                    awards += 1
                    aw += award_rows(rel, source="Germany", prefix="DEA", country="DEU")
                    continue
                row = tender_row(rel, source="oeffentlichevergabe (Germany)", prefix="DE", country="DEU", lang="de",
                                 access="GPA/EU open", today_s=str(t),
                                 link=f"https://www.oeffentlichevergabe.de/ui/en/search/details?noticeId={rel.get('id', '')}")
                if row:
                    new.append(row)
    # award history back-fill (supplier universe): 20 older days per run, up to 12 months
    st = PRIVATE / "germany_award_days.txt"
    done = set(st.read_text().split()) if st.exists() else set()
    back = [t - dt.timedelta(days=k) for k in range(days + 1, 366) if str(t - dt.timedelta(days=k)) not in done][:20]
    for d in back:
        r = s.get(URL, params={"pubDay": d.isoformat(), "format": "ocds.zip"}, timeout=180)
        if r.status_code != 200 or not r.content.startswith(b"PK"):
            continue
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for name in z.namelist():
            try:
                pkg = json.loads(z.read(name))
            except ValueError:
                continue
            for rel in pkg.get("releases", []):
                if {"award", "contract"} & set(rel.get("tag") or []):
                    aw += award_rows(rel, source="Germany", prefix="DEA", country="DEU")
        done.add(str(d))
    PRIVATE.mkdir(parents=True, exist_ok=True)
    st.write_text("\n".join(sorted(done)))
    save_awards("germany", aw)
    rows, _ = rolling("germany", new)
    log.info("Germany new %d, open %d, award releases seen %d", len(new), len(rows), awards)
    return rows, {"new": len(new), "awards_seen": awards, "awards_saved": len(aw)}
