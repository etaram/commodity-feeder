"""Price changes over time for the commodity panel.

Inputs : data/prices.csv (merged feed, written by feeder.run --merge), data/leads/price_series.csv (World Bank monthly)
Keeps  : data/leads/price_history.csv  (id,date,price - one row per commodity per price date)
Writes : data/leads/price_changes.json (what the web panel shows)

Changes are computed from our own stored history (grows every run) and, for Yahoo-sourced exchange
prices, from Yahoo's daily history (1 year), which gives all horizons immediately.
Run seed mode once (--seed) to rebuild history from git commits of data/prices.csv.
"""
import csv, json, subprocess, sys, time, io, os, re, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data/prices.csv"
HIST = ROOT / "data/leads/price_history.csv"
OUT = ROOT / "data/leads/price_changes.json"
HORIZONS = {"d1": 1, "d7": 7, "m1": 30, "m3": 90, "y1": 365}
SLACK = {"d1": 1, "d7": 3, "m1": 7, "m3": 15, "y1": 30}  # how far from the target date a snapshot may be


def num(v):
    try:
        return float(v)
    except Exception:
        return None


def read_prices(text=None):
    rows = csv.DictReader(io.StringIO(text) if text is not None else open(PRICES, encoding="utf-8"))
    out = []
    for r in rows:
        p = num(r.get("price_usd"))
        if r.get("id") and p and p > 0 and r.get("price_date"):
            out.append(r)
    return out


def load_hist():
    h = {}
    if HIST.exists():
        for r in csv.DictReader(open(HIST, encoding="utf-8")):
            p = num(r["price"])
            if p:
                h.setdefault(r["id"], {})[r["date"]] = p
    return h


def save_hist(h):
    with open(HIST, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "price"])
        for i in sorted(h):
            for d in sorted(h[i]):
                w.writerow([i, d, h[i][d]])


def seed_from_git(h):
    commits = subprocess.run(["git", "log", "--reverse", "--format=%H", "--", "data/prices.csv"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for c in commits:
        t = subprocess.run(["git", "show", f"{c}:data/prices.csv"], cwd=ROOT, capture_output=True, text=True).stdout
        for r in read_prices(t):
            h.setdefault(r["id"], {})[r["price_date"][:10]] = num(r["price_usd"])
    print(f"seeded from {len(commits)} commits")


def changes_from_hist(series, today):
    cur_date = max(series)
    cur = series[cur_date]
    base = dt.date.fromisoformat(cur_date)
    out = {}
    for k, days in HORIZONS.items():
        target = base - dt.timedelta(days=days)
        best = None
        for d, p in series.items():
            dd = dt.date.fromisoformat(d)
            if dd > target:
                continue
            gap = (target - dd).days
            if gap <= SLACK[k] and (best is None or gap < best[0]):
                best = (gap, p)
        out[k] = round((cur / best[1] - 1) * 100, 2) if best else None
    return out


def yahoo_changes(sym):
    import requests
    for base in ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"):
        try:
            r = requests.get(f"{base}/v8/finance/chart/{sym}", params={"range": "1y", "interval": "1d"}, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            res = r.json()["chart"]["result"][0]
            ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
            s = {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): c for t, c in zip(ts, cl) if c}
            return changes_from_hist(s, None) if len(s) > 3 else None
        except Exception as e:  # noqa: BLE001
            print("yahoo", sym, e)
        time.sleep(1.5)
    return None


def main():
    seed = "--seed" in sys.argv
    h = load_hist()
    if seed or not h:
        seed_from_git(h)
    rows = read_prices()
    for r in rows:
        h.setdefault(r["id"], {})[r["price_date"][:10]] = num(r["price_usd"])
    save_hist(h)

    items, ycount = [], 0
    for r in rows:
        tier = (r.get("tier") or "")[:2]
        ch = changes_from_hist(h[r["id"]], None)
        src = "stored history"
        m = re.search(r"/quote/([^/?\s]+)", r.get("link") or "")
        if m and "--no-yahoo" not in sys.argv:
            y = yahoo_changes(m.group(1))
            if y:
                ch, src, ycount = y, "Yahoo daily history", ycount + 1
        items.append({
            "id": r["id"], "name": r["name"], "hs6": r.get("hs6", ""), "price": num(r["price_usd"]), "unit": r.get("unit_usd", ""),
            "date": r["price_date"][:10], "source": r.get("source", ""), "tier": tier, "tier_name": r.get("tier", ""), "link": r.get("link", ""),
            "chg": ch, "chg_src": src if any(v is not None for v in ch.values()) else "",
        })

    wb = []
    p = ROOT / "data/leads/price_series.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            wb.append({"group": r["group"], "name": r["series"], "unit": r["unit"], "month": r["month"], "price": num(r["price"]),
                       "chg": {"m1": num(r["chg_1m_pct"]), "m3": num(r["chg_3m_pct"]), "y1": num(r["chg_12m_pct"])}})
    rl = {}
    try:
        rl = json.load(open(ROOT / "data/run_log.json"))
    except Exception:
        pass
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT.write_text(json.dumps({"updated_utc": now, "feed_finished_utc": (rl.get("finished_utc") or "") + ("Z" if rl.get("finished_utc") else ""),
                               "count": len(items), "items": items, "worldbank": wb}, separators=(",", ":")), encoding="utf-8")
    withch = sum(1 for i in items if i["chg_src"])
    print(f"price_changes: {len(items)} items, {withch} with changes, {ycount} from Yahoo history")


if __name__ == "__main__":
    main()
