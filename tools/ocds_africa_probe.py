"""Why do African OCDS publications yield no open tenders? Counts per file: releases, tender status, awards,
deadline and publish date ranges."""
import collections, gzip, io, json, sys, datetime as dt
sys.path.insert(0, ".")
from leads.common import session
BASE = "https://data.open-contracting.org/en"
PUBS = [("64", 2026), ("85", 2026), ("145", 2026), ("152", 2026), ("3", 2026), ("130", 2026), ("156", 2026), ("143", 2026), ("147", 2026), ("118", 2026)]
s = session()
today = str(dt.date.today())
for pid, y in PUBS:
    url = f"{BASE}/publication/{pid}/download?name={y}.jsonl.gz"
    try:
        r = s.get(url, stream=True, timeout=120)
    except Exception as e:
        print(pid, y, "ERR", e); continue
    print("==", pid, y, r.status_code, r.headers.get("content-length"), flush=True)
    if r.status_code != 200:
        continue
    st, n, aw, ctr, fut, nodl = collections.Counter(), 0, 0, 0, 0, 0
    pubmax, dlmax, keys = "", "", collections.Counter()
    sample = None
    with gzip.GzipFile(fileobj=r.raw) as gz:
        for line in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            n += 1
            try:
                rel = json.loads(line)
            except ValueError:
                continue
            if n == 1:
                keys.update(rel.keys())
            tn = rel.get("tender") or {}
            st[tn.get("status")] += 1
            aw += bool(rel.get("awards")); ctr += bool(rel.get("contracts"))
            dl = ((tn.get("tenderPeriod") or {}).get("endDate") or "")[:10]
            pubmax = max(pubmax, (rel.get("date") or "")[:10]); dlmax = max(dlmax, dl)
            if not dl: nodl += 1
            elif dl >= today:
                fut += 1
                if not sample: sample = {"ocid": rel.get("ocid"), "status": tn.get("status"), "awards": bool(rel.get("awards")), "method": tn.get("procurementMethod"), "details": tn.get("procurementMethodDetails"), "title": tn.get("title"), "dl": dl}
            if n >= 400000: break
    print(pid, "releases", n, "status", dict(st.most_common(6)), "with_awards", aw, "with_contracts", ctr,
          "deadline_future", fut, "no_deadline", nodl, "latest_release", pubmax, "latest_deadline", dlmax, "keys", list(keys)[:12], "sample", sample, flush=True)
