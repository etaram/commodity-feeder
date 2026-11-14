"""Shipping pulse from live AIS (AISStream.io, free WebSocket API, key in the AISSTREAM_API_KEY secret): for each
chokepoint and each port Sinder trades through, how many vessels report a position during a short listening window,
and how many of them are stopped (speed under 0.5 knot, or 'at anchor' / 'moored'). A rise in stopped vessels at a
port against its own 7-day average is an early sign of congestion; a drop of traffic in a strait is a sign of
diversion. Counts only: no vessel names or identifiers are stored or published.

Run every 8 hours from .github/workflows/biztrends.yml (listens LISTEN_S seconds). Output: data/leads/ais_pulse.csv
(pushed to the 'AIS Pulse' tab) and a rolling history in data/leads/cache/ais_history.json.
Coverage is terrestrial and satellite AIS as relayed by AISStream; some African and Middle East ports are thin, so
a zone with few reports is marked low coverage instead of read as empty."""
import asyncio
import csv
import json
import os
import time

from .common import CACHE, LEADS, log

URL = "wss://stream.aisstream.io/v0/stream"
LISTEN_S = int(os.environ.get("AIS_LISTEN_S", "540"))
ZONES = [  # name, kind, (lat_min, lon_min), (lat_max, lon_max)
    ("Suez Canal", "chokepoint", (29.5, 32.2), (31.6, 32.7)),
    ("Bab el-Mandeb", "chokepoint", (12.2, 42.8), (13.2, 43.8)),
    ("Strait of Hormuz", "chokepoint", (25.8, 55.8), (27.0, 57.2)),
    ("Panama Canal", "chokepoint", (8.8, -80.0), (9.5, -79.4)),
    ("Singapore Strait", "chokepoint", (1.0, 103.4), (1.5, 104.5)),
    ("Bosphorus", "chokepoint", (40.95, 28.9), (41.25, 29.15)),
    ("Gibraltar", "chokepoint", (35.8, -5.8), (36.2, -5.2)),
    ("Jebel Ali", "port", (24.9, 54.9), (25.1, 55.1)),
    ("Jeddah", "port", (21.3, 39.0), (21.6, 39.2)),
    ("Djibouti", "port", (11.55, 43.0), (11.7, 43.2)),
    ("Mombasa", "port", (-4.15, 39.55), (-3.95, 39.75)),
    ("Durban", "port", (-29.95, 30.95), (-29.8, 31.1)),
    ("Lagos (Apapa, Lekki)", "port", (6.25, 3.25), (6.5, 4.1)),
    ("Haifa", "port", (32.75, 34.95), (32.9, 35.05)),
    ("Ashdod", "port", (31.75, 34.55), (31.9, 34.7)),
    ("Shanghai (Yangshan)", "port", (30.5, 121.8), (31.5, 122.3)),
    ("Mumbai (JNPT)", "port", (18.85, 72.8), (19.0, 73.0)),
    ("Rotterdam", "port", (51.85, 3.9), (52.05, 4.3)),
    ("Santos", "port", (-24.05, -46.4), (-23.9, -46.25)),
]
HIST = CACHE / "ais_history.json"


def _zone(lat, lon):
    for name, _, (a, b), (c, d) in ZONES:
        if a <= lat <= c and b <= lon <= d:
            return name
    return None


async def listen(key, seconds):
    import websockets
    seen, stopped = {z[0]: set() for z in ZONES}, {z[0]: set() for z in ZONES}
    sub = {"APIKey": key, "BoundingBoxes": [[list(lo), list(hi)] for _, _, lo, hi in ZONES], "FilterMessageTypes": ["PositionReport"]}
    end = time.time() + seconds
    async with websockets.connect(URL, max_size=2 ** 22, open_timeout=30) as ws:
        await ws.send(json.dumps(sub))
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(1, end - time.time()))
            except asyncio.TimeoutError:
                break
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if m.get("error"):
                raise RuntimeError(str(m["error"])[:160])
            md, pr = m.get("MetaData") or {}, (m.get("Message") or {}).get("PositionReport") or {}
            z = _zone(md.get("latitude", 999), md.get("longitude", 999))
            if not z:
                continue
            mmsi = md.get("MMSI")
            seen[z].add(mmsi)
            if (pr.get("Sog") is not None and pr.get("Sog") < 0.5) or pr.get("NavigationalStatus") in (1, 5):
                stopped[z].add(mmsi)
    return {z: (len(seen[z]), len(stopped[z])) for z in seen}


def run():
    key = os.environ.get("AISSTREAM_API_KEY")
    if not key:
        log.info("AIS pulse: no AISSTREAM_API_KEY secret; skipped")
        return 0
    try:
        counts = asyncio.run(listen(key, LISTEN_S))
    except Exception as e:  # noqa: BLE001
        log.warning("AIS pulse failed: %s", str(e)[:200])
        return 0
    now = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
    try:
        hist = json.loads(HIST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hist = []
    hist = [h for h in hist if h.get("t", "") >= time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 86400))]
    rows = []
    for name, kind, _, _ in ZONES:
        v, s = counts.get(name, (0, 0))
        past = [h["c"][name] for h in hist if name in h.get("c", {})]
        av = sum(p[0] for p in past) / len(past) if past else None
        aa = sum(p[1] for p in past) / len(past) if past else None
        rows.append({"zone": name, "kind": kind, "vessels": v, "stopped": s,
                     "avg7_vessels": round(av, 1) if av is not None else "", "avg7_stopped": round(aa, 1) if aa is not None else "",
                     "chg_vessels_pct": round(100 * (v / av - 1), 1) if av else "", "chg_stopped_pct": round(100 * (s / aa - 1), 1) if aa else "",
                     "coverage": "low" if v < 3 else "ok", "sampled_utc": now, "minutes": round(LISTEN_S / 60)})
    hist.append({"t": now, "c": {k: list(v) for k, v in counts.items()}})
    HIST.parent.mkdir(parents=True, exist_ok=True)
    HIST.write_text(json.dumps(hist), encoding="utf-8")
    with open(LEADS / "ais_pulse.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info("AIS pulse: %d zones, %d vessels seen in %d min", len(rows), sum(r["vessels"] for r in rows), round(LISTEN_S / 60))
    return len(rows)


if __name__ == "__main__":
    run()
