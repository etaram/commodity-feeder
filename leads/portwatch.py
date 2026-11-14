"""Sea lanes and ports from IMF PortWatch (IMF + University of Oxford; satellite AIS, public ArcGIS API, no key).
Fills what the free terrestrial AIS feed cannot see (Suez, Bab el-Mandeb, Hormuz, Shanghai, Jebel Ali...): daily
transits per chokepoint by ship type and estimated tonnage, and daily port calls with import/export tonnes.

PortWatch publishes with a lag of about a week; every row carries its latest data date. Compared figures:
  avg7       ships per day over the latest 7 days
  chg_wow    against the 7 days before
  chg_yoy    against the same 7 days a year earlier (seasonality removed)
  chg_90     against the 90-day average
Output data/leads/portwatch.csv (pushed to the 'Port Watch' tab) with a 60-day daily series for a sparkline.
Licence: PortWatch data are free to use with attribution ("IMF PortWatch")."""
import csv
import datetime as dt
import json
import statistics
import time

from .common import LEADS, log, session

BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
CHOKE = f"{BASE}/Daily_Chokepoints_Data/FeatureServer/0/query"
PORTS = [f"{BASE}/Daily_Ports_Data/FeatureServer/0/query", f"{BASE}/Daily_Port_Data/FeatureServer/0/query"]
WANT_CHOKE = ["Suez Canal", "Bab el-Mandeb Strait", "Strait of Hormuz", "Panama Canal", "Malacca Strait", "Bosporus Strait",
              "Gibraltar Strait", "Cape of Good Hope", "Dover Strait", "Taiwan Strait"]
# the ports Sinder ships through (PortWatch names are matched with LIKE)
WANT_PORTS = {"Ashdod": "Ashdod", "Haifa": "Haifa", "Jebel Ali": "Jebel Ali", "Jeddah": "Jeddah", "Djibouti": "Djibouti", "Mombasa": "Mombasa",
              "Durban": "Durban", "Lagos (Apapa, Lekki)": "Apapa", "Shanghai (Yangshan)": "Shanghai", "Mumbai (JNPT)": "Nhava Sheva",
              "Rotterdam": "Rotterdam", "Santos": "Santos", "Mersin": "Mersin", "Port Said": "Port Said"}


def _q(s, url, where, fields, since):
    out, off = [], 0
    while True:
        r = s.get(url, params={"where": f"({where}) AND date >= '{since}'", "outFields": fields, "orderByFields": "date ASC",
                               "resultOffset": off, "resultRecordCount": 2000, "f": "json"}, timeout=90)
        r.raise_for_status()
        j = r.json()
        if j.get("error"):
            raise RuntimeError(str(j["error"])[:160])
        feats = [f.get("attributes") or {} for f in j.get("features") or []]
        out += feats
        if not j.get("exceededTransferLimit") or not feats:
            return out
        off += len(feats)
        time.sleep(0.5)


def _stats(series):
    """series: [(date, n)] ascending, daily"""
    if len(series) < 14:
        return {}
    d = {k: v for k, v in series}
    last = series[-1][0]
    L = dt.date.fromisoformat(last)
    win = lambda end, n: [d.get(str(end - dt.timedelta(days=i))) for i in range(n)]  # noqa: E731
    avg = lambda xs: statistics.mean([x for x in xs if x is not None]) if any(x is not None for x in xs) else None  # noqa: E731
    a7, p7 = avg(win(L, 7)), avg(win(L - dt.timedelta(days=7), 7))
    y7, a90 = avg(win(L - dt.timedelta(days=364), 7)), avg(win(L, 90))
    pc = lambda a, b: round(100 * (a / b - 1), 1) if a is not None and b else ""  # noqa: E731
    return {"date": last, "avg7": round(a7, 1) if a7 is not None else "", "chg_wow": pc(a7, p7), "chg_yoy": pc(a7, y7), "chg_90": pc(a7, a90),
            "series": " ".join(str(int(d.get(str(L - dt.timedelta(days=i)), 0) or 0)) for i in range(59, -1, -1))}


def run():
    s = session()
    since = str(dt.date.today() - dt.timedelta(days=400))
    rows = []
    try:
        names = " OR ".join(f"portname = '{n}'" for n in WANT_CHOKE)
        got = _q(s, CHOKE, names, "date,portname,n_total,n_tanker,n_container,n_dry_bulk,capacity", since)
        by = {}
        for a in got:
            by.setdefault(a["portname"], []).append(a)
        for name in WANT_CHOKE:
            xs = sorted(by.get(name, []), key=lambda a: a["date"])
            st = _stats([(a["date"], a.get("n_total") or 0) for a in xs])
            if not st:
                continue
            last7 = xs[-7:]
            tot = sum(a.get("n_total") or 0 for a in last7) or 1
            cap = _stats([(a["date"], a.get("capacity") or 0) for a in xs])
            rows.append({"kind": "chokepoint", "name": name, **st, "tanker_pct": round(100 * sum(a.get("n_tanker") or 0 for a in last7) / tot),
                         "container_pct": round(100 * sum(a.get("n_container") or 0 for a in last7) / tot), "bulk_pct": round(100 * sum(a.get("n_dry_bulk") or 0 for a in last7) / tot),
                         "tonnage_chg_yoy": cap.get("chg_yoy", ""), "imports_t7": "", "exports_t7": "", "zone": "", "source": "IMF PortWatch"})
        log.info("PortWatch chokepoints: %d of %d (data to %s)", len(rows), len(WANT_CHOKE), max((r["date"] for r in rows), default="-"))
    except Exception as e:  # noqa: BLE001
        log.warning("PortWatch chokepoints failed: %s", str(e)[:200])
    nport = 0
    for url in PORTS:
        try:
            where = " OR ".join(f"portname LIKE '%{v}%'" for v in WANT_PORTS.values())
            got = _q(s, url, where, "date,portname,country,portcalls,portcalls_container,portcalls_tanker,portcalls_dry_bulk,import,export", since)
        except Exception as e:  # noqa: BLE001
            log.warning("PortWatch ports (%s): %s", url.rsplit("/", 3)[-3], str(e)[:160]); continue
        by = {}
        for a in got:
            by.setdefault(a.get("portname") or "", []).append(a)
        for zone, key in WANT_PORTS.items():
            cand = [n for n in by if key.lower() in n.lower()]
            if not cand:
                continue
            name = max(cand, key=lambda n: sum(a.get("portcalls") or 0 for a in by[n]))   # the main port of that name
            log.info("PortWatch %s -> %s (candidates: %s)", zone, name, "; ".join(f"{n} {round(sum(a.get('portcalls') or 0 for a in by[n]) / max(1, len(by[n])), 1)}/day" for n in cand[:6]))
            xs = sorted(by[name], key=lambda a: a["date"])
            st = _stats([(a["date"], a.get("portcalls") or 0) for a in xs])
            if not st:
                continue
            last7 = xs[-7:]
            rows.append({"kind": "port", "name": name, **st, "tanker_pct": "", "container_pct": "", "bulk_pct": "", "tonnage_chg_yoy": "",
                         "imports_t7": round(sum(a.get("import") or 0 for a in last7)), "exports_t7": round(sum(a.get("export") or 0 for a in last7)),
                         "zone": zone, "source": "IMF PortWatch"})
            nport += 1
        break
    log.info("PortWatch ports: %d of %d", nport, len(WANT_PORTS))
    if not rows:
        return 0
    cols = ["kind", "name", "zone", "date", "avg7", "chg_wow", "chg_yoy", "chg_90", "tanker_pct", "container_pct", "bulk_pct", "tonnage_chg_yoy", "imports_t7", "exports_t7", "series", "source"]
    with open(LEADS / "portwatch.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    run()
