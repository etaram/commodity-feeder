"""Historical statistics per commodity price series (upgrade brief section 11): changes, rolling volatility,
seasonality and basic anomaly detection. All arithmetic in code; no model calls.

Inputs
  data/leads/price_history.csv           id,date,price - our own stored snapshots (grows every run)
  data/leads/commodity_prices.csv        names, links (a Yahoo link gives a symbol for the 1-year daily history)
  data/leads/cache/commodity_daily.json  cache of Yahoo daily closes per symbol (refreshed when older than a day)
  data/leads/pinksheet_monthly.csv       World Bank Pink Sheet monthly series (written here when the download works,
                                         read from the cached file otherwise); series listed in leads.price_trends.SERIES
Output
  data/leads/commodity_stats.csv  one row per id (and one per Pink Sheet series, id "WB:<series>") with
    freq, n_points, first_date, last_date, last_price, chg_1w_pct, chg_1m_pct, chg_3m_pct, chg_12m_pct,
    vol_30d, vol_90d (annualised stdev of log returns, only with 20+ points in the window),
    season_idx (12 numbers, calendar-month index, only with 24+ months of monthly data), season_note (why blank),
    anomaly (flags: sigma3 | jump15 | stale), anomaly_note, basis (the data window used)

Run: python -m leads.commodity_stats [--no-network]
"""
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEADS = ROOT / "data/leads"
HIST = LEADS / "price_history.csv"
PRICES = LEADS / "commodity_prices.csv"
DAILY_CACHE = LEADS / "cache/commodity_daily.json"
PINK = LEADS / "pinksheet_monthly.csv"
OUT = LEADS / "commodity_stats.csv"

HORIZONS = {"1w": 7, "1m": 30, "3m": 91, "12m": 365}
SLACK = {"1w": 3, "1m": 7, "3m": 15, "12m": 30}
MIN_VOL_POINTS = 20
MIN_SEASON_MONTHS = 24
# stale limits per cadence: a daily series older than 10 days has stopped updating; weekly and monthly series carry a
# publication lag (Eurostat unit values for a month arrive about two months later), so their limits are wider
STALE_DAYS = {"daily": 10, "weekly": 21, "monthly": 100}
CADENCE_RX = [(r"\bdaily\b|front month|futures|cash settlement", "daily"), (r"\bweekly\b|auction", "weekly"),
              (r"trade unit value|\bmonthly\b|export price", "monthly")]
FIELDS = ["id", "name", "freq", "n_points", "first_date", "last_date", "last_price", "chg_1w_pct", "chg_1m_pct", "chg_3m_pct", "chg_12m_pct",
          "vol_30d", "vol_90d", "season_idx", "season_note", "anomaly", "anomaly_note", "basis"]


def _d(s):
    return dt.date.fromisoformat(str(s)[:10])


def _clean(series):
    """{date str: price} -> sorted list of (date, price) with positive finite prices only."""
    out = []
    for k, v in series.items():
        try:
            p = float(v)
            if p > 0 and math.isfinite(p):
                out.append((_d(k), p))
        except Exception:
            continue
    return sorted(out)


def cadence_hint(price_type):
    """The publication cadence a price_type text states (daily, weekly, monthly) or ''."""
    for rx, c in CADENCE_RX:
        if re.search(rx, price_type or "", re.I):
            return c
    return ""


def frequency(pts, hint=""):
    """daily | weekly | monthly | sparse from the median spacing of the points; with under 3 points the stated
    cadence of the source (hint) is used, else sparse."""
    if len(pts) < 3:
        return hint or "sparse"
    gaps = sorted((b[0] - a[0]).days for a, b in zip(pts, pts[1:]))
    med = gaps[len(gaps) // 2]
    return "daily" if med <= 2 else "weekly" if med <= 9 else "monthly" if med <= 35 else "sparse"


def changes(pts):
    """Percentage change from the point nearest each horizon (within the slack), else None."""
    if not pts:
        return {k: None for k in HORIZONS}
    last_d, last_p = pts[-1]
    out = {}
    for k, days in HORIZONS.items():
        target = last_d - dt.timedelta(days=days)
        best = None
        for d, p in pts:
            if d > target:
                break
            gap = (target - d).days
            if gap <= SLACK[k] and (best is None or gap < best[0]):
                best = (gap, p)
        out[k] = round((last_p / best[1] - 1) * 100, 2) if best else None
    return out


def volatility(pts, window_days, freq=None):
    """Annualised stdev of log returns of the points inside the trailing window; None with under 20 points.
    Daily points annualise with sqrt(252), weekly with sqrt(52); sparse or monthly series give None."""
    if len(pts) < MIN_VOL_POINTS:
        return None
    freq = freq or frequency(pts)
    per_year = {"daily": 252, "weekly": 52}.get(freq)
    if not per_year:
        return None
    cutoff = pts[-1][0] - dt.timedelta(days=window_days)
    w = [p for d, p in pts if d >= cutoff]
    if len(w) < MIN_VOL_POINTS:
        return None
    rets = [math.log(b / a) for a, b in zip(w, w[1:]) if a > 0 and b > 0]
    if len(rets) < 2:
        return None
    return round(statistics.stdev(rets) * math.sqrt(per_year) * 100, 2)


def monthly_means(pts):
    """Calendar-month averages {(year, month): mean price} from any spacing."""
    acc = {}
    for d, p in pts:
        acc.setdefault((d.year, d.month), []).append(p)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def seasonality(monthly):
    """Ratio-to-centred-moving-average seasonal index per calendar month (12 values, mean 1.0).
    Returns (indices or None, note). Needs 24+ consecutive-ish months."""
    keys = sorted(monthly)
    if len(keys) < MIN_SEASON_MONTHS:
        return None, f"{len(keys)} months of data, {MIN_SEASON_MONTHS} needed"
    vals = [monthly[k] for k in keys]
    ratios = {m: [] for m in range(1, 13)}
    for i in range(6, len(vals) - 6):
        # centred 12-month moving average (2x12 MA): half weight on the two end months
        ma = (0.5 * vals[i - 6] + sum(vals[i - 5:i + 6]) + 0.5 * vals[i + 6]) / 12.0
        if ma > 0:
            ratios[keys[i][1]].append(vals[i] / ma)
    if any(len(r) < 1 for r in ratios.values()):
        return None, "not every calendar month is covered"
    idx = {m: sum(r) / len(r) for m, r in ratios.items()}
    norm = sum(idx.values()) / 12.0
    return [round(idx[m] / norm, 3) for m in range(1, 13)], f"{len(keys)} months, ratio to centred 12-month average"


def anomalies(pts, today, freq=None):
    """Flags for the last point: sigma3 (over 3 stdev from the trailing 30-day mean), jump15 (last move over 15%),
    stale (last point older than the frequency's limit). Returns (flags list, notes list)."""
    flags, notes = [], []
    if not pts:
        return flags, notes
    freq = freq or frequency(pts)
    last_d, last_p = pts[-1]
    cutoff = last_d - dt.timedelta(days=30)
    w = [p for d, p in pts[:-1] if d >= cutoff]
    if len(w) >= 10:
        mean = sum(w) / len(w)
        sd = statistics.pstdev(w)
        if sd > 0 and abs(last_p - mean) > 3 * sd:
            flags.append("sigma3")
            notes.append(f"last {last_p:g} is {abs(last_p - mean) / sd:.1f} stdev from the 30-day mean {mean:.4g}")
        elif sd == 0 and last_p != mean:
            flags.append("sigma3")
            notes.append(f"last {last_p:g} differs from a flat 30-day window at {mean:.4g}")
    if len(pts) >= 2:
        # a day-on-day move: the two last points must be close (10 days covers a weekly series)
        pd, pp = pts[-2]
        if (last_d - pd).days <= 10 and pp > 0:
            mv = (last_p / pp - 1) * 100
            if abs(mv) > 15:
                flags.append("jump15")
                notes.append(f"{mv:+.1f}% from {pd.isoformat()} to {last_d.isoformat()}")
    age = (today - last_d).days
    if freq in STALE_DAYS and age > STALE_DAYS[freq]:
        flags.append("stale")
        notes.append(f"last point {last_d.isoformat()} is {age} days old ({freq} series)")
    return flags, notes


def stats_row(sid, name, series, today, basis_prefix="", hint=""):
    """One output row from {date: price}. Pure. hint: the stated cadence when the points are too few to tell."""
    pts = _clean(series)
    freq = frequency(pts, hint)
    ch = changes(pts)
    row = {"id": sid, "name": name, "freq": freq, "n_points": len(pts),
           "first_date": pts[0][0].isoformat() if pts else "", "last_date": pts[-1][0].isoformat() if pts else "",
           "last_price": f"{pts[-1][1]:.6g}" if pts else ""}
    for k in HORIZONS:
        row[f"chg_{k}_pct"] = "" if ch[k] is None else ch[k]
    v30, v90 = volatility(pts, 30, freq), volatility(pts, 90, freq)
    row["vol_30d"] = "" if v30 is None else v30
    row["vol_90d"] = "" if v90 is None else v90
    idx, note = seasonality(monthly_means(pts))
    row["season_idx"] = json.dumps(idx) if idx else ""
    row["season_note"] = note
    flags, notes = anomalies(pts, today, freq)
    row["anomaly"] = ";".join(flags)
    row["anomaly_note"] = "; ".join(notes)
    vol_note = "" if v30 is not None or v90 is not None else f"; volatility needs {MIN_VOL_POINTS}+ daily or weekly points in the window"
    row["basis"] = f"{basis_prefix}{freq} {row['first_date']}..{row['last_date']}, {len(pts)} points{vol_note}" if pts else "no points"
    return row


# ---------------------------------------------------------------- data access (network optional, cached)

def load_history():
    h = {}
    if HIST.exists():
        for r in csv.DictReader(open(HIST, encoding="utf-8")):
            h.setdefault(r["id"], {})[r["date"][:10]] = r["price"]
    return h


def load_prices():
    return list(csv.DictReader(open(PRICES, encoding="utf-8"))) if PRICES.exists() else []


def yahoo_daily(symbols, network=True):
    """{symbol: {date: close}} from the cache, refreshed from Yahoo (1 year, daily) when the cache is older than a day."""
    cache = {}
    if DAILY_CACHE.exists():
        try:
            cache = json.loads(DAILY_CACHE.read_text())
        except Exception:
            cache = {}
    today = dt.date.today().isoformat()
    if network and os.environ.get("NO_NETWORK", "") == "":
        import requests
        changed = False
        for sym in symbols:
            if cache.get(sym, {}).get("fetched") == today:
                continue
            for base in ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"):
                try:
                    r = requests.get(f"{base}/v8/finance/chart/{sym}", params={"range": "1y", "interval": "1d"}, timeout=30,
                                     headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code != 200:
                        continue
                    res = r.json()["chart"]["result"][0]
                    ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
                    s = {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): c for t, c in zip(ts, cl) if c}
                    if len(s) > 3:
                        cache[sym] = {"fetched": today, "series": s}
                        changed = True
                    break
                except Exception as e:  # noqa: BLE001
                    print("yahoo", sym, type(e).__name__, file=sys.stderr)
        if changed:
            DAILY_CACHE.parent.mkdir(parents=True, exist_ok=True)
            DAILY_CACHE.write_text(json.dumps(cache, separators=(",", ":")))
    return {k: v.get("series", {}) for k, v in cache.items()}, {k: v.get("fetched", "") for k, v in cache.items()}


def pinksheet_monthly(network=True, keep_months=180):
    """{series name: {YYYY-MM-01: price}} for the Pink Sheet series in price_trends.SERIES, from the download when it
    works (then written to data/leads/pinksheet_monthly.csv) and from that file otherwise."""
    data = {}
    if network and os.environ.get("NO_NETWORK", "") == "":
        try:
            from . import price_trends
            url = price_trends._xlsx_url()
            if url:
                raw, units = price_trends._monthly(url)
                low = {k.lower(): k for k in raw}
                wanted = [k for keys in price_trends.SERIES.values() for k in keys]
                for k in wanted:
                    name = next((v for lk, v in low.items() if lk.startswith(k)), None)
                    if name and name not in data:
                        ser = raw[name]
                        months = sorted(ser)[-keep_months:]
                        data[name] = {"unit": units.get(name, ""), "series": {f"{m[:4]}-{m[5:7]}-01": ser[m] for m in months}}
                with open(PINK, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["series", "unit", "month", "price"])
                    for name, d in data.items():
                        for m, p in sorted(d["series"].items()):
                            w.writerow([name, d["unit"], m[:7], p])
                print(f"pink sheet: {len(data)} series written to {PINK.name}")
        except Exception as e:  # noqa: BLE001
            print("pink sheet download failed:", type(e).__name__, str(e)[:120], file=sys.stderr)
    if not data and PINK.exists():
        for r in csv.DictReader(open(PINK, encoding="utf-8")):
            data.setdefault(r["series"], {"unit": r["unit"], "series": {}})["series"][r["month"] + "-01"] = r["price"]
    return data


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    network = "--no-network" not in argv
    today = dt.date.today()
    hist = load_history()
    prices = load_prices()
    names = {r["id"]: r.get("commodity", "") for r in prices}
    hints = {r["id"]: cadence_hint(f"{r.get('price_type', '')} {r.get('quality', '')}") for r in prices}
    sym_of = {}
    for r in prices:
        m = re.search(r"/quote/([^/?\s]+)", r.get("link") or "")
        if m:
            sym_of[r["id"]] = m.group(1)
    daily, fetched = yahoo_daily(sorted(set(sym_of.values())), network)

    rows, n_yahoo = [], 0
    current = {r["id"]: (r.get("date", "")[:10], r.get("price_usd", "")) for r in prices if r.get("date") and r.get("price_usd")}
    for sid in sorted(set(hist) | set(names)):
        series, prefix = dict(hist.get(sid, {})), "price_history.csv "
        if sid in current:
            series.setdefault(current[sid][0], current[sid][1])  # the current feed row is a point too
        sym = sym_of.get(sid)
        if sym and daily.get(sym):
            # the exchange history is the better series: daily closes for a year, our snapshots fill the last days
            series = {**daily[sym], **series}
            prefix = f"Yahoo {sym} daily (fetched {fetched.get(sym, '')}) + price_history.csv "
            n_yahoo += 1
        rows.append(stats_row(sid, names.get(sid, ""), series, today, prefix, hints.get(sid, "")))

    pink = pinksheet_monthly(network)
    for name, d in sorted(pink.items()):
        rows.append(stats_row(f"WB:{name}", f"{name} {d.get('unit', '')}".strip(), d["series"], today, "World Bank Pink Sheet monthly ", "monthly"))

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    n_anom = sum(1 for r in rows if r["anomaly"])
    n_season = sum(1 for r in rows if r["season_idx"])
    n_vol = sum(1 for r in rows if r["vol_30d"] != "" or r["vol_90d"] != "")
    n_chg = sum(1 for r in rows if any(r[f"chg_{k}_pct"] != "" for k in HORIZONS))
    flags = {}
    for r in rows:
        for fl in r["anomaly"].split(";"):
            if fl:
                flags[fl] = flags.get(fl, 0) + 1
    print(f"commodity_stats: {len(rows)} series ({n_yahoo} with Yahoo daily history, {len(pink)} Pink Sheet), {n_chg} with a change, "
          f"{n_vol} with volatility, {n_season} with seasonality, {n_anom} anomalies {flags}")
    return rows


if __name__ == "__main__":
    main()
