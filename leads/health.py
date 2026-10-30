"""Source health for the tender collectors: reads data/leads/status.csv (written by the merge) and the previous
data/leads/health.json, flags sources that are empty, failed, stale or that lost more than half their rows, and
writes data/leads/health.json. Exit code 1 when the merge itself failed, so the Actions run turns red."""
import csv
import datetime as dt
import json
import sys

from .common import LEADS

STALE_H = 36       # a source not refreshed in 36 hours is stale (heavy sources run twice a day)
DROP = 0.5         # losing more than half the rows since the last run is suspicious


def main():
    now = dt.datetime.now(dt.timezone.utc)
    prev = {}
    try:
        prev = {s["source"]: s for s in json.loads((LEADS / "health.json").read_text()).get("sources", [])}
    except Exception:  # noqa: BLE001
        pass
    rows = []
    try:
        rows = list(csv.DictReader(open(LEADS / "status.csv", encoding="utf-8")))
    except Exception:  # noqa: BLE001
        pass
    out, alerts = [], []
    for r in rows:
        name = r["source"]
        n = int(float(r.get("rows") or 0))
        age = None
        try:
            age = round((now - dt.datetime.fromisoformat(r["last_run_utc"]).replace(tzinfo=dt.timezone.utc)).total_seconds() / 3600, 1)
        except Exception:  # noqa: BLE001
            pass
        p = prev.get(name, {}).get("rows")
        flags = []
        if r.get("note") != "OK":
            flags.append(r.get("note") or "NOT_OK")
        if n == 0:
            flags.append("zero rows")
        if p and n < p * DROP:
            flags.append(f"rows fell from {p} to {n}")
        if age is not None and age > STALE_H:
            flags.append(f"stale {age} h")
        if (LEADS / f"error_{name}.txt").exists():
            flags.append("error file present")
        out.append({"source": name, "rows": n, "prev_rows": p, "age_h": age, "flags": flags})
        if flags:
            alerts.append(f"{name}: {', '.join(flags)}")
    (LEADS / "health.json").write_text(json.dumps({"generated": now.strftime("%Y-%m-%dT%H:%MZ"), "alerts": alerts, "sources": out}, indent=1))
    for a in alerts:
        print("HEALTH ALERT", a)
    print(f"health: {len(out)} sources, {len(alerts)} alerts")
    if (LEADS / "error_merge.txt").exists():
        print("HEALTH ALERT merge failed - see error_merge.txt")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
